/**
 * LoRaWAN driver, from first principles.
 * Manual OTAA join + ABP-style uplinks using RadioLib for radio only.
 * RAK3172 (STM32WLE5). Region selected via TTN_REGION_* in config.h.
 */
#include "lorawan.h"
#include "config.h"
#include "power_adc.h"
#include "power_manager.h"   /* for power_manager_kick_watchdog */
#include "ctt_decode.h"      /* CTT tag frame decode (pure logic) */
#include <RadioLib.h>

/* Bench-soak build (env:stratolink_soak sets RELAY_SOLAR_MIN_MV=0) needs SubGhz.cpp
 * pulled into the link: a fresh env's LDF resolves RadioLib but not the framework's
 * SubGhz library, so SubGhzClass::* go undefined at link.  This shim makes a project
 * source depend on it (compiled with that env's -I) so SubGhz.cpp is built+linked.
 * The flight build (env:stratolink, RELAY_SOLAR_MIN_MV=3000) skips it entirely. */
#if defined(RELAY_SOLAR_MIN_MV) && (RELAY_SOLAR_MIN_MV == 0)
#include <SubGhz.h>
#endif

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
static uint32_t fCntDown = 0;      /* downlink frame counter (replay guard) */
static uint32_t s_tx_end_ms = 0;   /* millis() at end of the last uplink TX (RX-window timing) */
static uint8_t  s_tx_ch = 0;       /* channel index the last uplink used (for the RX1 downlink freq) */

/* OTAA credentials from secrets.h, parsed at init */
static uint8_t devEUI[8];
static uint8_t joinEUI[8];
static uint8_t appKey[16];

/* ========== Region Configuration ========== */
typedef struct {
    const float *tx_freqs;  uint8_t tx_ch_count;
    float rx2_freq;
    float rx1_base;  float rx1_step;  uint8_t rx1_mod; /* 0 = RX1 matches TX freq */
    uint8_t join_sf;  float join_bw;
    uint8_t rx1_sf;   float rx1_bw;
    uint8_t rx2_sf;   float rx2_bw;
    float init_freq;
    uint8_t tx_sf;    float tx_bw;
} lora_region_t;

/* Uplink SF is 9 in every region (the last tx_sf field of each table).
 * Rationale (analysis/antenna/05_sf_linkbudget.md): SF9 buys +5 dB sensitivity
 * over SF7 (~2x link-budget range, past the 412 km radio horizon at 10 km), the
 * single biggest lever on a link that ran at the SF7 floor on flight-3.  Cost is
 * airtime: SF9 ToA ~308 ms vs SF7 ~98 ms for the 35-byte payload, so the FULL-
 * tier cadence moves to 1200 s (config.h) to stay at ~22 s/day = 74% of the TTN
 * 30 s/day FUP (comfortable margin for join retries / clock drift).  JOIN SF is
 * unchanged (SF10 US/AU, SF7 EU/AS); that config is flight-proven, only uplinks
 * move to SF9.  RX1 SF matches join_sf via each region's RX1DROffset=0 mapping
 * (the previous code hardcoded rx1_sf=10 for US915/AU915 regardless of join, so
 * joins only ever succeeded via the RX2 fallback). */
static const float US915_FREQS[] = {903.9,904.1,904.3,904.5,904.7,904.9,905.1,905.3};
static const lora_region_t LORA_US915 = {
    /* US915 sub-band 2.  Join at DR0 (SF10/125), RX1 at DR10 (SF10/500)
     * per RP002 RX1 data-rate offset 0, this is the only join SF that
     * matches our rx1_sf without computing the DR2→DR8/DR3→DR8 cross-DR
     * mapping at runtime.  Yesterday's flight firmware ran this config
     * and joined cleanly through onethreenine gateway at -45 dBm.
     * Uplinks tx_sf=9 (DR1) for range; uplinks don't open RX windows in
     * our minimal LoRaWAN code, so the rx1_sf mismatch is irrelevant in
     * practice. */
    US915_FREQS, 8, 923.3,  923.3, 0.6, 8,
    10, 125.0,  10, 500.0,  12, 500.0,  904.1,  9, 125.0
};

static const float EU868_FREQS[] = {868.1, 868.3, 868.5};
static const lora_region_t LORA_EU868 = {
    EU868_FREQS, 3, 869.525,  0, 0, 0, /* RX1 = TX freq */
    7, 125.0,  7, 125.0,  9, 125.0,  868.1,  9, 125.0
};

static const float AU915_FREQS[] = {916.8,917.0,917.2,917.4,917.6,917.8,918.0,918.2};
static const lora_region_t LORA_AU915 = {
    /* AU915 same RP002 RX1 rule as US915, join at DR0/SF10 to match
     * RX1 DR10/SF10/500 without cross-DR offset math.  See US915
     * block above for the rationale. */
    AU915_FREQS, 8, 923.3,  923.3, 0.6, 8,
    10, 125.0,  10, 500.0,  12, 500.0,  917.0,  9, 125.0
};

static const float AS923_FREQS[] = {923.2, 923.4};
static const lora_region_t LORA_AS923 = {
    AS923_FREQS, 2, 923.2,  0, 0, 0, /* RX1 = TX freq */
    7, 125.0,  7, 125.0,  10, 125.0,  923.2,  9, 125.0
};

/* REGION is a mutable copy of one of the const tables above, switched
 * at runtime by lorawan_set_region() based on GPS-derived geofence
 * (region_manager.cpp).  Default at boot = US915, overwritten on the
 * first region check after a valid GPS fix.  Copying the struct (vs
 * a const reference) lets the same call sites work unchanged. */
static lora_region_t REGION = LORA_US915;
static lora_region_id_t REGION_ID = LORA_REGION_US915;

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

    /* TX on random channel */
    uint8_t ch = chIdx % REGION.tx_ch_count; chIdx++;
    radio->setFrequency(REGION.tx_freqs[ch]);
    radio->setSpreadingFactor(REGION.join_sf);
    radio->setBandwidth(REGION.join_bw);
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

    /* RX1: 5s after TX.  Kick the IWDG before the busy-wait: a single
     * TX-then-RX1-then-RX2 round can take ~7 s, plus the outer retry
     * delay (~3-7 s), multiple iterations under the 15 s lorawan_join
     * timeout from main loop() leave only a thin margin to the 32.7 s
     * watchdog.  Refresh here so the dog only catches genuine hangs. */
    power_manager_kick_watchdog();
    float rx1Freq = REGION.rx1_mod
        ? (REGION.rx1_base + (ch % REGION.rx1_mod) * REGION.rx1_step)
        : REGION.tx_freqs[ch];
    while (millis() - txEnd < 4500) delay(1);

    radio->setFrequency(rx1Freq);
    radio->setSpreadingFactor(REGION.rx1_sf);
    radio->setBandwidth(REGION.rx1_bw);
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

    /* RX2: 6s after TX */
    if (!received && (millis() - txEnd < 7000)) {
        radio->setFrequency(REGION.rx2_freq);
        radio->setSpreadingFactor(REGION.rx2_sf);
        radio->setBandwidth(REGION.rx2_bw);

        state = radio->receive(rxBuf, 33);
        if (state == RADIOLIB_ERR_NONE) {
            rxLen = radio->getPacketLength();
            received = true;
            LOG("[OTAA] Received in RX2!");
        }
    }

    radio->invertIQ(false); /* restore for uplinks */

    /* Restore TX config from active region, previously hardcoded to
     * SF10/BW125 (US915 default) which silently corrupted uplinks in
     * any other region. */
    radio->setSpreadingFactor(REGION.tx_sf);
    radio->setBandwidth(REGION.tx_bw);
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
    fCntDown = 0;
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
/* ========== Per-region OTAA credentials ==========
 *
 * TTN community network enforces globally-unique DevEUIs across all
 * clusters (nam1, eu1).  To get telemetry in multiple LoRaWAN regions
 * during a circumnavigation, each frequency plan needs its own
 * (DevEUI, AppKey) pair registered on the appropriate cluster.  The
 * flight firmware switches credentials when lorawan_set_region fires
 * a transition, so the next OTAA join uses the right identity for
 * the gateway listening below.
 *
 * Empty string = no creds for that region → lorawan_join returns
 * false immediately (firmware still respects geofence spectrum rules
 * via the SILENT/region-table channels, just won't transmit OTAA
 * traffic without valid credentials).
 *
 * JoinEUI is shared (TTN convention 00...00) and loaded once in
 * lorawan_init from LORAWAN_APP_EUI.
 *
 * Backward compatibility: older secrets files (secrets_board1.h,
 * secrets_board2.h) only define the legacy LORAWAN_DEV_EUI /
 * LORAWAN_APP_KEY pair.  The #ifndef guards below let those builds
 * succeed by mapping the legacy pair into the US915 slot and leaving
 * EU/AS/AU empty, single-region behaviour, same as before. */
#ifndef LORAWAN_DEV_EUI_US
#define LORAWAN_DEV_EUI_US LORAWAN_DEV_EUI
#endif
#ifndef LORAWAN_APP_KEY_US
#define LORAWAN_APP_KEY_US LORAWAN_APP_KEY
#endif
#ifndef LORAWAN_DEV_EUI_EU
#define LORAWAN_DEV_EUI_EU ""
#endif
#ifndef LORAWAN_APP_KEY_EU
#define LORAWAN_APP_KEY_EU ""
#endif
#ifndef LORAWAN_DEV_EUI_AS
#define LORAWAN_DEV_EUI_AS ""
#endif
#ifndef LORAWAN_APP_KEY_AS
#define LORAWAN_APP_KEY_AS ""
#endif
#ifndef LORAWAN_DEV_EUI_AU
#define LORAWAN_DEV_EUI_AU ""
#endif
#ifndef LORAWAN_APP_KEY_AU
#define LORAWAN_APP_KEY_AU ""
#endif

typedef struct {
    const char* dev_eui_hex;
    const char* app_key_hex;
} region_creds_t;

static const region_creds_t REGION_CREDS[LORA_REGION_COUNT] = {
    /* Indexed by lora_region_id_t.  Order must match the enum in
     * lorawan.h: US915=0, EU868=1, AS923=2, AU915=3, SILENT=4. */
    { LORAWAN_DEV_EUI_US, LORAWAN_APP_KEY_US },
    { LORAWAN_DEV_EUI_EU, LORAWAN_APP_KEY_EU },
    { LORAWAN_DEV_EUI_AS, LORAWAN_APP_KEY_AS },
    { LORAWAN_DEV_EUI_AU, LORAWAN_APP_KEY_AU },
    { "",                  ""                  },  /* SILENT */
};

static bool creds_loaded = false;

static void load_creds_for_current_region(void) {
    creds_loaded = false;
    if (REGION_ID >= LORA_REGION_SILENT) return;
    const region_creds_t* c = &REGION_CREDS[REGION_ID];
    if (!c->dev_eui_hex || c->dev_eui_hex[0] == '\0' ||
        !c->app_key_hex || c->app_key_hex[0] == '\0') return;
    hexToBytes(c->dev_eui_hex, devEUI, 8);
    hexToBytes(c->app_key_hex, appKey, 16);
    creds_loaded = true;
}

bool lorawan_creds_loaded(void) { return creds_loaded; }
void lorawan_get_dev_eui(uint8_t* out) { if (out) memcpy(out, devEUI, 8); }

bool lorawan_init(void) {
    HAL_ResumeTick();
    radio = new STM32WLx(new STM32WLx_Module());
    radio->setRfSwitchTable(rfswitch_pins, rfswitch_table);

    int16_t state = radio->begin(REGION.init_freq, REGION.tx_bw, 9, 7,
                                 RADIOLIB_SX126X_SYNC_WORD_PUBLIC,
                                 14, 8, 1.7, false);
    LOGV("[LoRaWAN] radio.begin: ", state);
    if (state != RADIOLIB_ERR_NONE) return false;

    radio->setSpreadingFactor(REGION.tx_sf);
    radio->setBandwidth(REGION.tx_bw);
    radio->setCodingRate(5);
    radio->setPreambleLength(8);
    radio->setCRC(true);

    /* JoinEUI is shared across regions; DevEUI + AppKey are loaded
     * per-region by load_creds_for_current_region (called below and
     * also from lorawan_set_region on every transition). */
    hexToBytes(LORAWAN_APP_EUI, joinEUI, 8);
    load_creds_for_current_region();

    LOG("[LoRaWAN] init OK");
    return true;
}

bool lorawan_join(uint32_t timeout_ms) {
    if (!radio) return false;
    if (REGION_ID == LORA_REGION_SILENT) return false;  /* off-plan zone */
    if (!creds_loaded) {
        LOG("[LoRaWAN] no OTAA creds for current region, skipping join");
        return false;
    }

    /* Skip the join if VSTOR is too low to reliably support +14 dBm TX
     * peaks (~50 mA bursts).  Below ~3.0 V the buck is in dropout and
     * Vdd droops hard during TX, failed joins burn the supercap fast
     * (the IWDG-reset-then-rejoin spiral observed empirically drains
     * 1.7 V in 4-5 minutes).  Returning false here lets loop() proceed
     * to a normal cycle which then sleeps; setup() retries join on the
     * next cold boot, by which point either solar has recharged the cap
     * or the chip browns out gracefully and waits. */
    if (power_adc_read_vSTOR_mv() < 3000) {
        LOG("[LoRaWAN] vstor too low to join");
        return false;
    }

    /* Wake the SX1262 from SLEEP retention (set by lorawan_sleep() on
     * the previous cycle) before any join-request TX.  Without this
     * the setFrequency()/transmit() calls in otaa_join() run against a
     * sleeping radio and the join silently fails forever, matches
     * lorawan_send_uplink()'s explicit standby() pattern. */
    radio->standby();

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
    if (REGION_ID == LORA_REGION_SILENT) return false;  /* off-plan zone */

    /* Bring the SX1262 into STDBY_RC before any per-packet reconfig.  After
     * lorawan_sleep() the radio is in SLEEP retention; setFrequency() and
     * other config writes are not guaranteed to apply in SLEEP mode, so an
     * explicit standby() is required for channel hopping to work across
     * STOP2 cycles. */
    radio->standby();

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

    s_tx_ch = (uint8_t)(chIdx % REGION.tx_ch_count);
    float freq = REGION.tx_freqs[s_tx_ch]; chIdx++;
    radio->setFrequency(freq);
    int16_t state = radio->transmit(pkt, idx);
    s_tx_end_ms = millis();
    LOGV("[LoRaWAN] uplink: ", state);
    if (state == RADIOLIB_ERR_NONE) { fCntUp++; return true; }
    return false;
}

bool lorawan_joined(void) { return _joined; }

void lorawan_sleep(void) {
    /* SX1262 SLEEP w/ retention. ~3 µA. Next transmit() implicitly wakes it
     * (RadioLib calls setStandby before configuring TX). Without this, the
     * radio stays in STDBY_RC across STOP2, both kills the energy budget
     * and seems to trigger a hard reset on the RAK3172 module on STOP2 entry. */
    if (radio) (void)radio->sleep(true);
}

/* ========== Meshtastic open-relay (mission-subordinate, power-gated) ==========
 *
 * A header-only, KEYLESS LongFast repeater that runs on the SHARED SX1262 in the
 * idle time between TTN cycles, ONLY when the caller says power allows.  The
 * 16-byte Meshtastic PacketHeader is plaintext, so we forward real traffic
 * (dedup + hop-decrement + airtime cap) WITHOUT any channel PSK, "relay what we
 * hear, register nothing."  Validated on a live mesh 2026-06-03 (RESULTS.md).
 *
 * SAFETY (defense in depth): the caller (main.cpp) gates entry on FULL tier +
 * solar + !burst; this window additionally (a) self-aborts the instant
 * VSTOR < floor_mv, (b) caps its own TX airtime, (c) yields by max_ms so the next
 * TTN cycle is on time, and (d) on EVERY exit restores the EXACT post-init
 * LoRaWAN TX PHY (SF9/BW125/CR5/sync-PUBLIC/preamble-8/CRC) that send_uplink()
 * depends on.  The LoRaWAN session (DevAddr/keys/FCnt) is never touched. */

/* Meshtastic LongFast default-channel centre per region.  0 => not relay-eligible
 * (we only TX Meshtastic where the frequency is validated + practically legal). */
static float meshtastic_longfast_freq(lora_region_id_t id) {
    switch (id) {
        case LORA_REGION_US915: return 906.875f;  /* US LongFast slot 19 */
        case LORA_REGION_EU868: return 869.525f;  /* EU LongFast */
        default:                return 0.0f;       /* AS923/AU915/SILENT: disabled */
    }
}

/* Forwarded-frame dedup ring (managed-flood good-citizen: never re-forward the
 * same (from,id) twice).  Persists across windows for stronger suppression. */
#define RELAY_DEDUP_N 32
static uint32_t s_dd_from[RELAY_DEDUP_N];
static uint32_t s_dd_id[RELAY_DEDUP_N];
static uint8_t  s_dd_head = 0;
static bool relay_dd_seen(uint32_t f, uint32_t i) {
    for (uint8_t k = 0; k < RELAY_DEDUP_N; k++)
        if (s_dd_from[k] == f && s_dd_id[k] == i) return true;
    return false;
}
static void relay_dd_mark(uint32_t f, uint32_t i) {
    s_dd_from[s_dd_head] = f; s_dd_id[s_dd_head] = i;
    s_dd_head = (uint8_t)((s_dd_head + 1) % RELAY_DEDUP_N);
}
static inline uint32_t relay_rd_u32le(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static volatile bool s_relay_rx = false;
static void relay_rx_isr(void) { s_relay_rx = true; }
static lorawan_relay_stats_t s_relay = {0};
static uint8_t s_relay_buf[256];

void lorawan_relay_get_stats(lorawan_relay_stats_t* out) { if (out) *out = s_relay; }

/* Restore the exact post-init LoRaWAN TX PHY that send_uplink()/join depend on.
 * Frequency is restored too (TTN paths set it per-TX, but this honors the
 * "post-init state" contract and removes the off-channel trap of leaving the
 * radio tuned to the Meshtastic frequency). */
static void relay_restore_lorawan_phy(void) {
    radio->standby();
    radio->setFrequency(REGION.init_freq);
    radio->setSpreadingFactor(REGION.tx_sf);
    radio->setBandwidth(REGION.tx_bw);
    radio->setCodingRate(5);
    radio->setSyncWord(RADIOLIB_SX126X_SYNC_WORD_PUBLIC);
    radio->setPreambleLength(8);
    radio->setCRC(true);
    radio->invertIQ(false);
}

uint32_t lorawan_relay_window(uint32_t max_ms, uint16_t floor_mv) {
    if (!radio) return 0;
    float freq = meshtastic_longfast_freq(REGION_ID);
    if (freq <= 0.0f) return 0;                    /* region not relay-eligible */

    uint32_t start = millis();

    /* Switch the shared radio to Meshtastic LongFast (SF11/BW250/CR4-5,
     * sync 0x2B, 16-symbol preamble, explicit header + CRC, non-inverted IQ). */
    radio->standby();
    radio->setFrequency(freq);
    radio->setSpreadingFactor(11);
    radio->setBandwidth(250.0);
    radio->setCodingRate(5);
    radio->setSyncWord(0x2B);
    radio->setPreambleLength(16);
    radio->setCRC(true);
    radio->invertIQ(false);

    s_relay_rx = false;
    radio->setPacketReceivedAction(relay_rx_isr);
    if (radio->startReceive() != RADIOLIB_ERR_NONE) {
        radio->clearPacketReceivedAction();
        relay_restore_lorawan_phy();
        return millis() - start;
    }

    uint32_t tx_airtime_ms = 0;
    uint32_t last_hk = start;
    while (millis() - start < max_ms) {
        if (s_relay_rx) {
            s_relay_rx = false;
            size_t len = radio->getPacketLength();
            if (len >= 16 && len <= sizeof(s_relay_buf) &&
                radio->readData(s_relay_buf, len) == RADIOLIB_ERR_NONE) {
                s_relay.rx_count++;
                s_relay.last_rssi = (int16_t)radio->getRSSI();
                uint8_t  flags = s_relay_buf[12];
                uint8_t  hop   = flags & 0x07;
                uint32_t from  = relay_rd_u32le(s_relay_buf + 4);
                uint32_t id    = relay_rd_u32le(s_relay_buf + 8);
                s_relay.last_from = from;
                if (hop == 0) {
                    s_relay.hop0++;                         /* hop-exhausted: drop */
                } else if (relay_dd_seen(from, id)) {
                    s_relay.dedup++;                        /* already forwarded */
                } else {
                    uint32_t elapsed = millis() - start;
                    /* airtime self-cap: keep our TX <= RELAY_AIRTIME_CAP_PCT% of the window */
                    if (tx_airtime_ms == 0 ||
                        tx_airtime_ms * 100u < (uint32_t)RELAY_AIRTIME_CAP_PCT * elapsed) {
                        relay_dd_mark(from, id);
                        s_relay_buf[12] = (uint8_t)((flags & ~0x07) | (hop - 1)); /* hop-1 */
                        s_relay_buf[15] = 0xD1;             /* relay_node marker (our forward) */
                        uint32_t t0 = millis();
                        if (radio->transmit(s_relay_buf, len) == RADIOLIB_ERR_NONE) {
                            s_relay.fwd++;
                            tx_airtime_ms += (millis() - t0);
                        }
                    } else {
                        s_relay.cap_skip++;
                    }
                }
            }
            s_relay_rx = false;
            radio->startReceive();
        }
        uint32_t now = millis();
        if (now - last_hk >= 1000) {                        /* housekeeping ~1 Hz */
            last_hk = now;
            power_manager_kick_watchdog();
            if (power_adc_read_vSTOR_mv() < floor_mv) break; /* floor-abort: protect mission reserve */
            if (power_manager_freefall_pending()) break;    /* freefall: yield to burst NOW, not at window end */
            if (power_adc_read_solar_mv() < RELAY_SOLAR_MIN_MV) break; /* sunset/cloud mid-window: the
                * relay only runs on solar surplus, and a 20 min window can outlive
                * the daylight that justified opening it */
        }
        delay(2);
    }

    radio->clearPacketReceivedAction();
    relay_restore_lorawan_phy();
    return millis() - start;
}

/* ===== CTT wildlife-tag listener (RX-only 434 MHz FSK window) =====
 *
 * Listens for CTT LifeTag/PowerTag/HybridTag beacons (the Motus network's
 * 434 MHz tags on birds/bats) in the solar-surplus idle window and logs
 * decoded tag ids.  RX-only: transmits nothing, registers nowhere.  PHY per
 * the rtl_433 decoder + CTT's own RadioLib test-tag firmware: 2-FSK 25 kbps,
 * +-25 kHz deviation, no shaping, sync D3 91, fixed 5-byte payload (4 id
 * bytes from a 32-symbol dictionary + CRC-8), one ~3 ms beep every 2-15 s.
 *
 * Same subordination contract as the relay window: the caller gates entry,
 * the 1 Hz housekeeping aborts on VSTOR floor, solar loss, or a pending
 * freefall, and the exact LoRaWAN PHY is restored on every exit.  Note the
 * board's front end is matched for 868/915; RX at 434 works with reduced
 * sensitivity, bench-quantified with an SDR-generated test beep. */

static volatile bool s_ctt_rx = false;
static void ctt_rx_isr(void) { s_ctt_rx = true; }
static lorawan_ctt_stats_t s_ctt = {0};
static ctt_detection_t s_ctt_log[CTT_LOG_N];
static uint8_t s_ctt_log_n = 0;

void lorawan_ctt_get_stats(lorawan_ctt_stats_t* out) { if (out) *out = s_ctt; }
uint8_t lorawan_ctt_get_log(ctt_detection_t* out) {
    if (out) memcpy(out, s_ctt_log, sizeof(s_ctt_log));
    return s_ctt_log_n;
}

/* Log a decoded frame, aggregating repeat beeps of the same tag within one
 * window (a LifeTag beeps every ~5 s; a pass would otherwise flood the ring). */
static void ctt_log_frame(uint32_t id_raw, uint32_t id_motus, uint8_t motus_valid,
                          int16_t rssi, uint16_t window_idx) {
    for (uint8_t i = 0; i < s_ctt_log_n; i++) {
        if (s_ctt_log[i].id_raw == id_raw && s_ctt_log[i].window_idx == window_idx) {
            if (s_ctt_log[i].hits < 255) s_ctt_log[i].hits++;
            if (rssi > s_ctt_log[i].rssi_best) s_ctt_log[i].rssi_best = rssi;
            return;
        }
    }
    uint8_t slot;
    if (s_ctt_log_n < CTT_LOG_N) {
        slot = s_ctt_log_n++;
    } else {
        slot = (uint8_t)(s_ctt.tags_seen % CTT_LOG_N);  /* ring: overwrite oldest-ish */
    }
    s_ctt_log[slot].id_raw      = id_raw;
    s_ctt_log[slot].id_motus    = id_motus;
    s_ctt_log[slot].rssi_best   = rssi;
    s_ctt_log[slot].hits        = 1;
    s_ctt_log[slot].motus_valid = motus_valid;
    s_ctt_log[slot].window_idx  = window_idx;
    s_ctt.tags_seen++;
}

/* Return the shared radio from FSK to the exact post-init LoRaWAN state.
 * beginFSK() switched the SX126x packet type, so a full LoRa begin() is
 * required before the parameter-level restore. */
static void ctt_restore_lorawan(void) {
    (void)radio->begin(REGION.init_freq, REGION.tx_bw, 9, 7,
                       RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 14, 8, 1.7, false);
    relay_restore_lorawan_phy();
}

uint32_t lorawan_ctt_window(uint32_t max_ms, uint16_t floor_mv) {
    if (!radio) return 0;
    uint32_t start = millis();

    radio->standby();
    int16_t st = radio->beginFSK((float)CTT_FREQ_MHZ, 25.0, 25.0, 50.0, 0, 16);
    if (st == RADIOLIB_ERR_NONE) st = radio->setDataShaping(RADIOLIB_SHAPING_NONE);
    uint8_t ctt_sync[2] = {0xD3, 0x91};
    if (st == RADIOLIB_ERR_NONE) st = radio->setSyncWord(ctt_sync, 2);
    if (st == RADIOLIB_ERR_NONE) st = radio->fixedPacketLengthMode(5);
    if (st == RADIOLIB_ERR_NONE) st = radio->setCRC(0);  /* tag CRC-8 checked in software */
    if (st != RADIOLIB_ERR_NONE) {
        ctt_restore_lorawan();
        return millis() - start;
    }

    s_ctt.windows++;
    uint16_t widx = (uint16_t)s_ctt.windows;
    s_ctt_rx = false;
    radio->setPacketReceivedAction(ctt_rx_isr);
    if (radio->startReceive() != RADIOLIB_ERR_NONE) {
        radio->clearPacketReceivedAction();
        ctt_restore_lorawan();
        return millis() - start;
    }

    uint32_t last_hk = start;
    while (millis() - start < max_ms) {
        if (s_ctt_rx) {
            s_ctt_rx = false;
            uint8_t buf[5];
            if (radio->readData(buf, 5) == RADIOLIB_ERR_NONE) {
                s_ctt.frames_rx++;
                ctt_frame_t f;
                if (ctt_decode(buf, &f)) {
                    int16_t rssi = (int16_t)radio->getRSSI();
                    s_ctt.last_id   = f.id_raw;
                    s_ctt.last_rssi = rssi;
                    ctt_log_frame(f.id_raw, f.id_motus, f.motus_valid ? 1 : 0, rssi, widx);
                } else {
                    s_ctt.crc_fail++;
                }
            }
            s_ctt_rx = false;
            if (radio->startReceive() != RADIOLIB_ERR_NONE) break;  /* re-arm failed: bail, don't busy-loop deaf */
        }
        uint32_t now = millis();
        if (now - last_hk >= 1000) {                    /* housekeeping ~1 Hz */
            last_hk = now;
            power_manager_kick_watchdog();
            if (power_adc_read_vSTOR_mv() < floor_mv) break;
            if (power_manager_freefall_pending()) break;
            if (power_adc_read_solar_mv() < RELAY_SOLAR_MIN_MV) break;
        }
        delay(2);
    }

    radio->clearPacketReceivedAction();
    ctt_restore_lorawan();
    return millis() - start;
}

/* ========== Class-A downlink (command channel) ========== */

/* Downlink MIC, identical to compute_mic but with the direction byte = 1. */
static void compute_mic_down(const uint8_t *msg, size_t msgLen, uint32_t fc, uint8_t *mic) {
    uint8_t blk0[16] = {0x49,0,0,0,0,0x01};
    blk0[6]=devAddr&0xFF; blk0[7]=(devAddr>>8)&0xFF;
    blk0[8]=(devAddr>>16)&0xFF; blk0[9]=(devAddr>>24)&0xFF;
    blk0[10]=fc&0xFF; blk0[11]=(fc>>8)&0xFF; blk0[12]=(fc>>16)&0xFF; blk0[13]=(fc>>24)&0xFF;
    blk0[15]=(uint8_t)msgLen;
    uint8_t buf[96]; memcpy(buf,blk0,16); memcpy(buf+16,msg,msgLen);
    aes_cmac(nwkSKey, buf, 16+msgLen, mic);
}

/* One bounded RX window: arm RX, poll for RxDone until deadline_ms, read it. Bounded
 * so a slow-DR RX1 cannot block past the RX2 window. Caller sets the PHY first. */
static volatile bool s_dl_rx = false;
static void dl_rx_isr(void) { s_dl_rx = true; }
static size_t rx_window(uint8_t* buf, size_t maxlen, uint32_t deadline_ms) {
    s_dl_rx = false;
    radio->setPacketReceivedAction(dl_rx_isr);
    if (radio->startReceive() != RADIOLIB_ERR_NONE) {
        radio->clearPacketReceivedAction(); radio->standby(); return 0;
    }
    while ((int32_t)(millis() - deadline_ms) < 0) {
        if (s_dl_rx) break;
        power_manager_kick_watchdog();
        delay(2);
    }
    radio->clearPacketReceivedAction();
    size_t n = 0;
    if (s_dl_rx) {
        n = radio->getPacketLength();
        if (n > maxlen) n = maxlen;
        if (radio->readData(buf, n) != RADIOLIB_ERR_NONE) n = 0;
    }
    radio->standby();
    return n;
}

bool lorawan_receive_downlink(lorawan_downlink_t* out) {
    if (!radio || !_joined || !out) return false;
    float rx1f = REGION.rx1_mod
        ? (REGION.rx1_base + (s_tx_ch % REGION.rx1_mod) * REGION.rx1_step)
        : REGION.tx_freqs[s_tx_ch % REGION.tx_ch_count];

    uint8_t rx[64]; size_t rxLen = 0;
    radio->standby();
    radio->setSyncWord(RADIOLIB_SX126X_SYNC_WORD_PUBLIC);
    radio->setPreambleLength(8);
    radio->setCRC(false);            /* LoRaWAN downlinks carry no PHY CRC */
    radio->invertIQ(true);           /* downlinks use inverted IQ */

    /* RX1 at RECEIVE_DELAY1 (1 s): uplink-channel downlink freq, data DR (SF = tx_sf). */
    while ((int32_t)(millis() - s_tx_end_ms) < 960) { power_manager_kick_watchdog(); delay(2); }
    radio->setFrequency(rx1f);
    radio->setSpreadingFactor(REGION.tx_sf);
    radio->setBandwidth(REGION.rx1_bw);
    rxLen = rx_window(rx, sizeof(rx), s_tx_end_ms + 1500);

    /* RX2 at RECEIVE_DELAY2 (2 s): fixed freq/DR from the region table (TTN-correct). */
    if (rxLen == 0) {
        while ((int32_t)(millis() - s_tx_end_ms) < 1960) { power_manager_kick_watchdog(); delay(2); }
        radio->setFrequency(REGION.rx2_freq);
        radio->setSpreadingFactor(REGION.rx2_sf);
        radio->setBandwidth(REGION.rx2_bw);
        rxLen = rx_window(rx, sizeof(rx), s_tx_end_ms + 2700);
    }

    radio->invertIQ(false);
    relay_restore_lorawan_phy();      /* leave the radio ready for the next uplink */
    if (rxLen < 12) return false;     /* MHDR(1) + FHDR(7) + MIC(4) minimum */

    if ((rx[0] & 0xE0) != 0x60) return false;   /* unconfirmed data-down only (no ACK path for confirmed) */
    uint32_t da = (uint32_t)rx[1] | ((uint32_t)rx[2]<<8) | ((uint32_t)rx[3]<<16) | ((uint32_t)rx[4]<<24);
    if (da != devAddr) return false;
    uint8_t foptsLen = rx[5] & 0x0F;

    /* Reconstruct the full 32-bit FCntDown from the 16-bit on-air value (the server uses
     * 32-bit for MIC + decrypt) and reject a backward (replayed) counter. */
    uint16_t lo = (uint16_t)(rx[6] | (rx[7] << 8));
    uint32_t fcnt;
    if (fCntDown == 0) {
        fcnt = lo;                                  /* first downlink of the session */
    } else {
        uint16_t diff = (uint16_t)(lo - (uint16_t)(fCntDown & 0xFFFFu));
        if (diff >= 0x8000u) return false;          /* counter moved backward = replay */
        fcnt = fCntDown + diff;                      /* forward, handles the 16-bit rollover */
    }

    size_t hdr = 8u + foptsLen;
    if (rxLen < hdr + 4) return false;
    uint8_t mic[4]; compute_mic_down(rx, rxLen - 4, fcnt, mic);
    if (memcmp(mic, &rx[rxLen - 4], 4) != 0) return false;     /* integrity */

    out->fport = 0; out->len = 0;
    if (rxLen > hdr + 4) {            /* FPort + FRMPayload present */
        uint8_t fport = rx[hdr];
        uint8_t frmLen = (uint8_t)(rxLen - hdr - 1 - 4);
        if (frmLen > sizeof(out->data)) frmLen = sizeof(out->data);
        const uint8_t* key = (fport == 0) ? nwkSKey : appSKey;
        aes_encrypt_payload(key, devAddr, fcnt, 1, &rx[hdr + 1], frmLen);  /* CTR decrypt, dir=1 */
        out->fport = fport;
        out->len = frmLen;
        memcpy(out->data, &rx[hdr + 1], frmLen);
    }
    fCntDown = fcnt + 1;
    return true;
}

/* ========== Runtime region switching ========== */

void lorawan_set_region(lora_region_id_t id) {
    if (id == REGION_ID) return;  /* no-op: same plan */

    /* Any region change invalidates the LoRaWAN session, TTN clusters
     * (nam1, eu1) are independent, DevAddr / NwkSKey / AppSKey from the
     * old region won't authenticate against the new gateway, and
     * fCntUp must reset to 0 (per-session replay protection).  Done
     * up-front so the SILENT branch below gets the same invalidation
     * as a "normal" region switch, caught by the hardware trajectory
     * test which flagged "fCntUp not reset on AS923->SILENT". */
    _joined = false;
    fCntUp  = 0;
    chIdx   = 0;

    switch (id) {
        case LORA_REGION_US915: REGION = LORA_US915; break;
        case LORA_REGION_EU868: REGION = LORA_EU868; break;
        case LORA_REGION_AS923: REGION = LORA_AS923; break;
        case LORA_REGION_AU915: REGION = LORA_AU915; break;
        case LORA_REGION_SILENT:
        default:
            REGION_ID = LORA_REGION_SILENT;
            creds_loaded = false;
            return;  /* skip radio reconfig, SILENT keeps prev band */
    }

    REGION_ID = id;
    load_creds_for_current_region();  /* swap DevEUI/AppKey for new band */

    /* Reconfigure the radio for the new region's TX defaults so any
     * subsequent join attempt fires on the right band. */
    if (radio) {
        radio->standby();
        radio->setFrequency(REGION.init_freq);
        radio->setBandwidth(REGION.tx_bw);
        radio->setSpreadingFactor(REGION.tx_sf);
    }
}

lora_region_id_t lorawan_current_region(void) { return REGION_ID; }

/* ========== Session persistence ========== */

void lorawan_export_session(lorawan_session_t* out) {
    if (!out) return;
    out->magic     = 0;  /* save layer fills magic + version */
    out->version   = 0;
    out->region_id = (uint32_t)REGION_ID;
    out->devAddr   = devAddr;
    out->fCntUp    = fCntUp;
    out->fCntDown  = fCntDown;
    memcpy(out->nwkSKey, nwkSKey, 16);
    memcpy(out->appSKey, appSKey, 16);
}

bool lorawan_import_session(const lorawan_session_t* in) {
    if (!in) return false;
    if (in->region_id >= (uint32_t)LORA_REGION_SILENT) return false;

    /* Apply region first so the radio is configured before the next
     * uplink attempt.  set_region clears _joined + fCntUp, then we
     * restore the saved session state on top. */
    REGION_ID = (lora_region_id_t)in->region_id;
    switch (REGION_ID) {
        case LORA_REGION_US915: REGION = LORA_US915; break;
        case LORA_REGION_EU868: REGION = LORA_EU868; break;
        case LORA_REGION_AS923: REGION = LORA_AS923; break;
        case LORA_REGION_AU915: REGION = LORA_AU915; break;
        default: return false;
    }
    devAddr = in->devAddr;
    fCntUp  = in->fCntUp;
    fCntDown = in->fCntDown;
    memcpy(nwkSKey, in->nwkSKey, 16);
    memcpy(appSKey, in->appSKey, 16);
    _joined = true;

    /* Also refresh DevEUI/AppKey for the restored region.  Uplinks
     * use session keys (NwkSKey/AppSKey), but if the session ever
     * gets invalidated (region switch, replay collision, etc.) we
     * need creds available for the rejoin.  No-op if the region has
     * no creds in secrets, uplinks still work with the restored
     * session keys, just any future rejoin will fail. */
    load_creds_for_current_region();

    if (radio) {
        radio->standby();
        radio->setFrequency(REGION.init_freq);
        radio->setBandwidth(REGION.tx_bw);
        radio->setSpreadingFactor(REGION.tx_sf);
    }
    return true;
}
