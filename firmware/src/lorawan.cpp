/**
 * LoRaWAN driver — from first principles.
 * Manual OTAA join + ABP-style uplinks using RadioLib for radio only.
 * RAK3172 (STM32WLE5), US915 FSB2 for TTN.
 */
#include "lorawan.h"
#include "config.h"
#include <RadioLib.h>

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
#define LOG(x) Serial.println(x)
#define LOGV(x,v) do { Serial.print(x); Serial.println(v); } while(0)
#else
#define LOG(x)    ((void)0)
#define LOGV(x,v) ((void)0)
#endif

static STM32WLx *radio = nullptr;
static bool _joined = false;

/* Session state (derived from OTAA join) */
static uint32_t devAddr = 0;
static uint8_t nwkSKey[16];
static uint8_t appSKey[16];
static uint32_t fCntUp = 0;

/* OTAA credentials from secrets.h — parsed at init */
static uint8_t devEUI[8];
static uint8_t joinEUI[8];
static uint8_t appKey[16];

/* US915 FSB2 */
static const float FSB2_FREQS[] = {903.9,904.1,904.3,904.5,904.7,904.9,905.1,905.3};
static const float RX2_FREQ = 923.3;
static uint8_t chIdx = 0;

/* RF switch */
static const uint32_t rfswitch_pins[] =
    {PB8, PC13, RADIOLIB_NC, RADIOLIB_NC, RADIOLIB_NC};
static const Module::RfSwitchMode_t rfswitch_table[] = {
    {STM32WLx::MODE_IDLE,  {LOW,  LOW}},
    {STM32WLx::MODE_RX,    {HIGH, LOW}},
    {STM32WLx::MODE_TX_HP, {HIGH, HIGH}},
    END_OF_MODE_TABLE,
};

/* ========== Software AES-128 ========== */
static const uint8_t sbox[256] = {
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
};
static const uint8_t rcon[11] = {0x00,0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36};

static void aes_key_expand(const uint8_t key[16], uint8_t rk[176]) {
    memcpy(rk, key, 16);
    for (int i=4;i<44;i++) {
        uint8_t t[4]; memcpy(t,&rk[(i-1)*4],4);
        if (i%4==0) { uint8_t tmp=t[0]; t[0]=sbox[t[1]]^rcon[i/4]; t[1]=sbox[t[2]]; t[2]=sbox[t[3]]; t[3]=sbox[tmp]; }
        for (int j=0;j<4;j++) rk[i*4+j]=rk[(i-4)*4+j]^t[j];
    }
}
static uint8_t xtime(uint8_t x) { return (x<<1)^((x>>7)*0x1b); }
static void aes_ecb_encrypt(const uint8_t key[16], const uint8_t in[16], uint8_t out[16]) {
    uint8_t rk[176],s[16]; aes_key_expand(key,rk);
    for (int i=0;i<16;i++) s[i]=in[i]^rk[i];
    for (int r=1;r<=10;r++) {
        uint8_t t[16]; for (int i=0;i<16;i++) t[i]=sbox[s[i]];
        s[0]=t[0];s[1]=t[5];s[2]=t[10];s[3]=t[15]; s[4]=t[4];s[5]=t[9];s[6]=t[14];s[7]=t[3];
        s[8]=t[8];s[9]=t[13];s[10]=t[2];s[11]=t[7]; s[12]=t[12];s[13]=t[1];s[14]=t[6];s[15]=t[11];
        if (r<10) { for (int i=0;i<4;i++) {
            uint8_t a=s[i*4],b=s[i*4+1],c=s[i*4+2],d=s[i*4+3];
            s[i*4]=xtime(a)^xtime(b)^b^c^d; s[i*4+1]=a^xtime(b)^xtime(c)^c^d;
            s[i*4+2]=a^b^xtime(c)^xtime(d)^d; s[i*4+3]=xtime(a)^a^b^c^xtime(d);
        }}
        for (int i=0;i<16;i++) s[i]^=rk[r*16+i];
    }
    memcpy(out,s,16);
}
static void aes_ecb_decrypt(const uint8_t key[16], const uint8_t in[16], uint8_t out[16]) {
    /* For join-accept: decrypt = encrypt (AES-ECB is used in decrypt direction) */
    /* LoRaWAN join-accept uses AES decrypt, but the server encrypts with AES encrypt,
     * so the device must use AES encrypt to "decrypt" it. */
    aes_ecb_encrypt(key, in, out);
}
static void shift_left_128(const uint8_t in[16], uint8_t out[16]) {
    for (int i=0;i<15;i++) out[i]=(in[i]<<1)|(in[i+1]>>7); out[15]=in[15]<<1;
}
static void aes_cmac(const uint8_t key[16], const uint8_t *msg, size_t len, uint8_t *mac) {
    uint8_t L[16]={0},K1[16],K2[16]; aes_ecb_encrypt(key,L,L);
    shift_left_128(L,K1); if(L[0]&0x80) K1[15]^=0x87;
    shift_left_128(K1,K2); if(K1[0]&0x80) K2[15]^=0x87;
    size_t n=(len+15)/16; if(!n) n=1;
    bool complete=(len>0)&&(len%16==0);
    uint8_t X[16]={0};
    for (size_t i=0;i<n-1;i++) { for(int j=0;j<16;j++) X[j]^=msg[i*16+j]; aes_ecb_encrypt(key,X,X); }
    uint8_t last[16]={0}; size_t ll=len-(n-1)*16; memcpy(last,msg+(n-1)*16,ll);
    if(complete) { for(int j=0;j<16;j++) last[j]^=K1[j]; }
    else { last[ll]=0x80; for(int j=0;j<16;j++) last[j]^=K2[j]; }
    for(int j=0;j<16;j++) X[j]^=last[j];
    aes_ecb_encrypt(key,X,X); memcpy(mac,X,4);
}
static void aes_encrypt_payload(const uint8_t key[16], uint32_t da, uint32_t fc, uint8_t dir, uint8_t *p, uint8_t len) {
    for (uint8_t i=0;i<(len+15)/16;i++) {
        uint8_t A[16]={0x01,0,0,0,0,dir};
        A[6]=da&0xFF;A[7]=(da>>8)&0xFF;A[8]=(da>>16)&0xFF;A[9]=(da>>24)&0xFF;
        A[10]=fc&0xFF;A[11]=(fc>>8)&0xFF;A[12]=(fc>>16)&0xFF;A[13]=(fc>>24)&0xFF;
        A[15]=i+1; uint8_t S[16]; aes_ecb_encrypt(key,A,S);
        for(uint8_t j=0;j<16&&(i*16+j)<len;j++) p[i*16+j]^=S[j];
    }
}

/* ========== Hex parsing ========== */
static void hexToBytes(const char *h, uint8_t *o, size_t n) {
    for (size_t i=0;i<n;i++) {
        uint8_t b=0;
        for (int j=0;j<2;j++) { b<<=4; char c=h[i*2+j];
            if(c>='0'&&c<='9') b|=c-'0'; else if(c>='A'&&c<='F') b|=c-'A'+10; else if(c>='a'&&c<='f') b|=c-'a'+10;
        } o[i]=b;
    }
}

/* ========== OTAA Join ========== */
static bool otaa_join(void) {
    /* Build join request: MHDR(1) + JoinEUI(8,LE) + DevEUI(8,LE) + DevNonce(2,LE) + MIC(4) = 23 bytes */
    uint8_t pkt[23];
    pkt[0] = 0x00; /* MHDR: join request */

    /* JoinEUI and DevEUI in LITTLE ENDIAN (reversed from display order) */
    for (int i=0;i<8;i++) pkt[1+i] = joinEUI[7-i];
    for (int i=0;i<8;i++) pkt[9+i] = devEUI[7-i];

    /* Random DevNonce */
    uint16_t devNonce = (uint16_t)(micros() & 0xFFFF);
    pkt[17] = devNonce & 0xFF;
    pkt[18] = (devNonce >> 8) & 0xFF;

    /* MIC over MHDR|JoinEUI|DevEUI|DevNonce using AppKey */
    aes_cmac(appKey, pkt, 19, &pkt[19]);

    /* TX on random FSB2 channel at SF10BW125 (DR0) */
    uint8_t ch = chIdx % 8; chIdx++;
    radio->setFrequency(FSB2_FREQS[ch]);
    radio->setSpreadingFactor(10);
    radio->setBandwidth(125.0);
    radio->setCRC(true);

    int16_t state = radio->transmit(pkt, 23);
    if (state != RADIOLIB_ERR_NONE) {
        LOGV("[OTAA] TX fail: ", state);
        return false;
    }
    LOG("[OTAA] Join request sent");
    unsigned long txEnd = millis();

    /* Ensure radio is fully back in standby before configuring RX */
    radio->standby();
    delay(5);

    uint8_t rxBuf[64];
    size_t rxLen = 0;
    bool received = false;

    /* RX1: 5s after TX, 923.3+(ch%8)*0.6 MHz, SF10BW500 (DR10) */
    float rx1Freq = 923.3 + (ch % 8) * 0.6;
    while (millis() - txEnd < 4500) delay(1);

    radio->setFrequency(rx1Freq);
    radio->setSpreadingFactor(10);
    radio->setBandwidth(500.0);
    radio->setCodingRate(5);
    radio->setSyncWord(RADIOLIB_SX126X_SYNC_WORD_PUBLIC);
    radio->setPreambleLength(8);
    radio->setCRC(false);
    radio->invertIQ(true);

    state = radio->receive(rxBuf, 33);
    if (state == RADIOLIB_ERR_NONE) {
        rxLen = radio->getPacketLength();
        received = true;
        LOG("[OTAA] Received in RX1!");
    }

    /* RX2: 6s after TX, 923.3 MHz, SF12BW500 (DR8) */
    if (!received && (millis() - txEnd < 7000)) {
        radio->setFrequency(RX2_FREQ);
        radio->setSpreadingFactor(12);

        state = radio->receive(rxBuf, 33);
        if (state == RADIOLIB_ERR_NONE) {
            rxLen = radio->getPacketLength();
            received = true;
            LOG("[OTAA] Received in RX2!");
        }
    }

    radio->invertIQ(false); /* restore for uplinks */

    /* Restore TX config */
    radio->setSpreadingFactor(10);
    radio->setBandwidth(125.0);
    radio->setCRC(true);

    if (!received) {
        LOG("[OTAA] No join-accept");
        return false;
    }
    LOGV("[OTAA] Received ", (int)rxLen);

    if (rxLen != 17 && rxLen != 33) {
        LOG("[OTAA] Bad length");
        return false;
    }

    /* Decrypt join-accept: first byte is MHDR (0x20), rest is AES-encrypted with AppKey */
    /* LoRaWAN: device uses AES ECB ENCRYPT (not decrypt) to decode join-accept */
    uint8_t dec[33];
    dec[0] = rxBuf[0]; /* MHDR not encrypted */
    for (size_t i = 1; i < rxLen; i += 16) {
        size_t blockLen = (rxLen - i >= 16) ? 16 : rxLen - i;
        uint8_t block[16] = {0};
        memcpy(block, &rxBuf[i], blockLen);
        aes_ecb_encrypt(appKey, block, &dec[i]);
    }

    /* Verify MIC: CMAC over MHDR|payload (excluding MIC) */
    uint8_t micCalc[4];
    aes_cmac(appKey, dec, rxLen - 4, micCalc);
    if (memcmp(micCalc, &dec[rxLen-4], 4) != 0) {
        LOG("[OTAA] MIC mismatch");
        return false;
    }
    LOG("[OTAA] Join-accept verified!");

    /* Parse join-accept: MHDR(1) + AppNonce(3) + NetID(3) + DevAddr(4) + DLSettings(1) + RxDelay(1) [+ CFList] + MIC(4) */
    uint8_t appNonce[3] = {dec[1], dec[2], dec[3]};
    /* uint8_t netID[3] = {dec[4], dec[5], dec[6]}; */
    devAddr = (uint32_t)dec[7] | ((uint32_t)dec[8]<<8) | ((uint32_t)dec[9]<<16) | ((uint32_t)dec[10]<<24);

    LOGV("[OTAA] DevAddr: 0x", devAddr);

    /* Derive session keys (LoRaWAN 1.0.x) */
    /* NwkSKey = aes128_encrypt(AppKey, 0x01|AppNonce|NetID|DevNonce|pad) */
    /* AppSKey = aes128_encrypt(AppKey, 0x02|AppNonce|NetID|DevNonce|pad) */
    uint8_t keyBlock[16] = {0};
    keyBlock[0] = 0x01;
    memcpy(&keyBlock[1], appNonce, 3);
    memcpy(&keyBlock[4], &dec[4], 3); /* NetID */
    keyBlock[7] = devNonce & 0xFF;
    keyBlock[8] = (devNonce >> 8) & 0xFF;
    aes_ecb_encrypt(appKey, keyBlock, nwkSKey);

    keyBlock[0] = 0x02;
    aes_ecb_encrypt(appKey, keyBlock, appSKey);

    fCntUp = 0;
    LOG("[OTAA] Session keys derived");
    return true;
}

/* ========== Uplink MIC ========== */
static void compute_mic(const uint8_t *msg, size_t msgLen, uint8_t *mic) {
    uint8_t blk0[16] = {0x49,0,0,0,0,0x00};
    blk0[6]=devAddr&0xFF; blk0[7]=(devAddr>>8)&0xFF;
    blk0[8]=(devAddr>>16)&0xFF; blk0[9]=(devAddr>>24)&0xFF;
    blk0[10]=fCntUp&0xFF; blk0[11]=(fCntUp>>8)&0xFF;
    blk0[12]=(fCntUp>>16)&0xFF; blk0[13]=(fCntUp>>24)&0xFF;
    blk0[15]=msgLen;
    uint8_t buf[96]; memcpy(buf,blk0,16); memcpy(buf+16,msg,msgLen);
    aes_cmac(nwkSKey, buf, 16+msgLen, mic);
}

/* ========== Public API ========== */
bool lorawan_init(void) {
    HAL_ResumeTick();
    radio = new STM32WLx(new STM32WLx_Module());
    radio->setRfSwitchTable(rfswitch_pins, rfswitch_table);

    int16_t state = radio->begin(904.1, 125.0, 9, 7,
                                 RADIOLIB_SX126X_SYNC_WORD_PUBLIC,
                                 14, 8, 1.7, false);
    LOGV("[LoRaWAN] radio.begin: ", state);
    if (state != RADIOLIB_ERR_NONE) return false;

    radio->setSpreadingFactor(10);
    radio->setBandwidth(125.0);
    radio->setCodingRate(5);
    radio->setPreambleLength(8);
    radio->setCRC(true);

    /* Parse credentials from secrets.h */
    hexToBytes(LORAWAN_DEV_EUI, devEUI, 8);
    hexToBytes(LORAWAN_APP_EUI, joinEUI, 8);
    hexToBytes(LORAWAN_APP_KEY, appKey, 16);

    LOG("[LoRaWAN] init OK");
    return true;
}

bool lorawan_join(uint32_t timeout_ms) {
    if (!radio) return false;

    unsigned long start = millis();
    while (millis() - start < timeout_ms) {
        if (otaa_join()) {
            _joined = true;
            LOG("[LoRaWAN] OTAA joined!");
            return true;
        }
        delay(3000 + (millis() & 0xFFF));
    }
    LOG("[LoRaWAN] join timeout");
    return false;
}

bool lorawan_send_uplink(const uint8_t* payload, uint8_t payload_len) {
    if (!radio || !_joined || !payload || payload_len > LORAWAN_PAYLOAD_MAX) return false;

    uint8_t pkt[80]; uint8_t idx = 0;
    pkt[idx++] = 0x40;
    pkt[idx++]=devAddr&0xFF; pkt[idx++]=(devAddr>>8)&0xFF;
    pkt[idx++]=(devAddr>>16)&0xFF; pkt[idx++]=(devAddr>>24)&0xFF;
    pkt[idx++]=0x00; pkt[idx++]=fCntUp&0xFF; pkt[idx++]=(fCntUp>>8)&0xFF;
    pkt[idx++]=1; /* FPort */
    memcpy(&pkt[idx], payload, payload_len);
    aes_encrypt_payload(appSKey, devAddr, fCntUp, 0, &pkt[idx], payload_len);
    idx += payload_len;
    uint8_t mic[4]; compute_mic(pkt, idx, mic);
    memcpy(&pkt[idx], mic, 4); idx += 4;

    float freq = FSB2_FREQS[chIdx % 8]; chIdx++;
    radio->setFrequency(freq);
    int16_t state = radio->transmit(pkt, idx);
    LOGV("[LoRaWAN] uplink: ", state);
    if (state == RADIOLIB_ERR_NONE) { fCntUp++; return true; }
    return false;
}

bool lorawan_joined(void) { return _joined; }
