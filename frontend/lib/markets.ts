export const MARKETS = [
  {
    id: 'sotorasib-ind',
    address: '0xb7Bd56113438961202EcFF985E7Cb2B9F2442475',
    program: 'sotorasib',
    milestone: 'IND filing',
    description:
      'Will the Investigational New Drug (IND) application for sotorasib be filed by the target date?',
    resolutionTarget: 'Q4 2026',
  },
  {
    id: 'adagrasib-ph2',
    address: '0x15c463dcc7393ce70B83a1Cd28F0C8859883e2B4',
    program: 'adagrasib',
    milestone: 'Phase 2 primary endpoint',
    description:
      "Will adagrasib's Phase 2 trial meet its primary endpoint by the target date?",
    resolutionTarget: 'Q2 2027',
  },
  {
    id: 'vepdegestrant-ph3',
    address: '0xA88A5781904e884eA0f8b2aFF749904c602055E6',
    program: 'vepdegestrant',
    milestone: 'Phase 3 success',
    description:
      "Will vepdegestrant's Phase 3 trial demonstrate statistically significant efficacy by the target date?",
    resolutionTarget: 'Q1 2028',
  },
  {
    id: 'bi1701963-approval',
    address: '0x1922A8823Ba0D49bacde732B1C97996BeDC42068',
    program: 'BI-1701963',
    milestone: 'FDA approval',
    description: 'Will BI-1701963 receive FDA approval by the target date?',
    resolutionTarget: 'Q4 2028',
  },
] as const;

export type Market = (typeof MARKETS)[number];
