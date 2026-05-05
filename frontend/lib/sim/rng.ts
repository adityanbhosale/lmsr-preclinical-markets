/**
 * Mulberry32 — fast, seedable PRNG. Identical sequence given identical seed.
 * Used everywhere in the sim. Never call Math.random() directly.
 */
export function mulberry32(seed: number): () => number {
    let s = seed >>> 0;
    return function () {
      s = (s + 0x6D2B79F5) >>> 0;
      let t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  
  /** Box-Muller — standard normal from two uniforms. */
  export function randn(rng: () => number): number {
    const u1 = Math.max(rng(), 1e-12);
    const u2 = rng();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }
  
  /** Sample from N(mu, sigma^2). */
  export function sampleNormal(rng: () => number, mu: number, sigma: number): number {
    return mu + sigma * randn(rng);
  }