import { createHash } from 'node:crypto';
import { chmod, mkdir } from 'node:fs/promises';
import { canonicalJson, newNonce, sha256, writeJson } from './files.ts';
import type { Mapping, Route } from './types.ts';

/**
 * A repeatable stream of random numbers from a seed: SHA-256 of "seed:counter", read 32 bits at a time. The same
 * seed always gives the same stream, so a shuffle can be redone to check it, and nothing about the stream hints at
 * the seed.
 */
export function seededRandom(seed: string): () => number {
  let counter = 0;
  let buffer: Buffer = Buffer.alloc(0);
  let offset = 0;
  return () => {
    if (offset + 4 > buffer.length) {
      buffer = createHash('sha256').update(`${seed}:${counter}`).digest();
      counter += 1;
      offset = 0;
    }
    const value = buffer.readUInt32BE(offset);
    offset += 4;
    return value / 0x100000000;
  };
}

/** Fisher-Yates, in place on a copy. */
export function shuffle<T>(items: readonly T[], random: () => number): T[] {
  const out = [...items];
  for (let index = out.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [out[index], out[swap]] = [out[swap] as T, out[index] as T];
  }
  return out;
}

/**
 * Which route sits in slot A, for `n` pairs: half the pairs put the first route in A and half the second (one more
 * for the first when n is odd), then the order is shuffled from the seed. Balanced, so neither route owns slot A.
 */
export function slotOrders(n: number, random: () => number): boolean[] {
  const flags = Array.from({ length: n }, (_, index) => index < Math.ceil(n / 2));
  return shuffle(flags, random);
}

/** The sha256 that pairs.json commits to: the mapping's pairs, its nonce and the eval id, key-sorted. */
export function mappingCommitment(mapping: Mapping): string {
  const pairs = [...mapping.pairs].sort((a, b) => (a.pair_id < b.pair_id ? -1 : 1));
  return sha256(canonicalJson({ eval_id: mapping.eval_id, nonce: mapping.nonce, pairs }));
}

export function newMapping(evalId: string, seed: string, entries: Array<{ pair_id: string; claim_id: string; A: Route; B: Route }>): Mapping {
  return { schema: 1, eval_id: evalId, seed, nonce: newNonce(), pairs: entries };
}

/** Write the mapping where the judge never looks: its folder is 0700 and the file 0600. */
export async function writeSealed(dir: string, file: string, mapping: Mapping): Promise<void> {
  await mkdir(dir, { recursive: true, mode: 0o700 });
  await chmod(dir, 0o700);
  await writeJson(file, mapping, 0o600);
}
