#!/usr/bin/env node
/* Generate non-secret interoperability vectors with Node/OpenSSL's AES.
 * This deliberately does not import firmware code. The resulting constants
 * are checked into test_lorawan_crypto.cpp so production framing is compared
 * against an independent implementation and crypto library. */
import assert from "node:assert/strict";
import { createCipheriv, createDecipheriv } from "node:crypto";

const block = (key, input) => {
  const cipher = createCipheriv("aes-128-ecb", key, null);
  cipher.setAutoPadding(false);
  return Buffer.concat([cipher.update(input), cipher.final()]);
};
/* LoRaWAN 1.0.x network-side join-accept encryption applies AES decrypt;
 * the end device decodes it with AES encrypt. */
const inverseBlock = (key, input) => {
  const decipher = createDecipheriv("aes-128-ecb", key, null);
  decipher.setAutoPadding(false);
  return Buffer.concat([decipher.update(input), decipher.final()]);
};
const shift = (input) => {
  const output = Buffer.alloc(16);
  for (let i = 0; i < 15; ++i) {
    output[i] = ((input[i] << 1) | (input[i + 1] >> 7)) & 0xff;
  }
  output[15] = (input[15] << 1) & 0xff;
  return output;
};
const xor = (left, right) =>
  Buffer.from(left.map((value, index) => value ^ right[index]));
const cmac = (key, message) => {
  const l = block(key, Buffer.alloc(16));
  const k1 = shift(l);
  if (l[0] & 0x80) k1[15] ^= 0x87;
  const k2 = shift(k1);
  if (k1[0] & 0x80) k2[15] ^= 0x87;
  const count = Math.max(1, Math.ceil(message.length / 16));
  let x = Buffer.alloc(16);
  for (let i = 0; i + 1 < count; ++i) {
    x = block(key, xor(x, message.subarray(i * 16, i * 16 + 16)));
  }
  const final = Buffer.alloc(16);
  const tail = message.subarray((count - 1) * 16);
  tail.copy(final);
  if (tail.length === 16) {
    for (let i = 0; i < 16; ++i) final[i] ^= k1[i];
  } else {
    final[tail.length] = 0x80;
    for (let i = 0; i < 16; ++i) final[i] ^= k2[i];
  }
  return block(key, xor(x, final));
};

/* Guard the independent generator itself with RFC 4493 example 1. */
assert.equal(
  cmac(Buffer.from("2b7e151628aed2a6abf7158809cf4f3c", "hex"), Buffer.alloc(0))
    .toString("hex"),
  "bb1d6929e95937287fa37d129b756746",
);

const key = Buffer.from("000102030405060708090a0b0c0d0e0f", "hex");
const nwkKey = Buffer.from("2b7e151628aed2a6abf7158809cf4f3c", "hex");
const devAddr = 0x26011bda;
const fCnt = 0x00010203;
const plain = Buffer.from(
  "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20",
  "hex",
);
const cryptFor = (direction) => {
  const crypt = Buffer.from(plain);
  for (let offset = 0, index = 1; offset < crypt.length; offset += 16, ++index) {
    const a = Buffer.alloc(16);
    a[0] = 1;
    a[5] = direction;
    a.writeUInt32LE(devAddr, 6);
    a.writeUInt32LE(fCnt, 10);
    a[15] = index;
    const stream = block(key, a);
    for (let i = 0; i < Math.min(16, crypt.length - offset); ++i) {
      crypt[offset + i] ^= stream[i];
    }
  }
  return crypt;
};

const message = Buffer.from("40da1b01260003010a010203040506070809", "hex");
const micFor = (direction) => {
  const b0 = Buffer.alloc(16);
  b0[0] = 0x49;
  b0[5] = direction;
  b0.writeUInt32LE(devAddr, 6);
  b0.writeUInt32LE(fCnt, 10);
  b0[15] = message.length;
  return cmac(nwkKey, Buffer.concat([b0, message])).subarray(0, 4);
};
const joinNonce = Buffer.from("010203", "hex");
const netId = Buffer.from("040506", "hex");
const makeKey = (type) => {
  const input = Buffer.alloc(16);
  input[0] = type;
  joinNonce.copy(input, 1);
  netId.copy(input, 4);
  input.writeUInt16LE(0x0708, 7);
  return block(key, input);
};
const joinEncrypted = Buffer.from(
  "00112233445566778899aabbccddeeffffeeddccbbaa99887766554433221100",
  "hex",
);
const joinAcceptFields = Buffer.from(
  "010203040506da1b01260005", "hex",
);
const joinAcceptMhdr = Buffer.from([0x20]);
const joinAcceptPlainBody = Buffer.concat([
  joinAcceptFields,
  cmac(key, Buffer.concat([joinAcceptMhdr, joinAcceptFields])).subarray(0, 4),
]);
assert.equal(joinAcceptPlainBody.length, 16);
const joinAcceptFrame = Buffer.concat([
  joinAcceptMhdr,
  inverseBlock(key, joinAcceptPlainBody),
]);
const cfList = Buffer.from("0102030405060708090a0b0c0d0e0f00", "hex");
const joinAcceptFieldsWithCf = Buffer.concat([joinAcceptFields, cfList]);
const joinAcceptPlainBodyWithCf = Buffer.concat([
  joinAcceptFieldsWithCf,
  cmac(key, Buffer.concat([
    joinAcceptMhdr, joinAcceptFieldsWithCf,
  ])).subarray(0, 4),
]);
assert.equal(joinAcceptPlainBodyWithCf.length, 32);
const joinAcceptFrameWithCf = Buffer.concat([
  joinAcceptMhdr,
  inverseBlock(key, joinAcceptPlainBodyWithCf),
]);

console.log(JSON.stringify({
  uplink_payload_ciphertext: cryptFor(0).toString("hex"),
  downlink_payload_ciphertext: cryptFor(1).toString("hex"),
  uplink_mic: micFor(0).toString("hex"),
  downlink_mic: micFor(1).toString("hex"),
  nwk_session_key: makeKey(1).toString("hex"),
  app_session_key: makeKey(2).toString("hex"),
  join_accept_plaintext: Buffer.concat([
    block(key, joinEncrypted.subarray(0, 16)),
    block(key, joinEncrypted.subarray(16, 32)),
  ]).toString("hex"),
  authenticated_join_accept_frame: joinAcceptFrame.toString("hex"),
  authenticated_join_accept_frame_with_cflist:
    joinAcceptFrameWithCf.toString("hex"),
}, null, 2));
