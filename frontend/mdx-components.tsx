/**
 * MDX component overrides — registered globally so any .mdx page can use
 * these without an explicit import.
 *
 * Custom widgets:
 *   <ContractAddress />     copy-to-clipboard address with explorer link
 *   <ArchitectureDiagram /> SVG of the dual-layer split
 *   <LiveMarketCard />      fetches live LSLMSR data via wagmi
 */

import { InteractiveL2Sim } from '@/components/docs/InteractiveL2Sim';
import type { MDXComponents } from 'mdx/types';
import { ContractAddress } from '@/components/docs/ContractAddress';
import { ArchitectureDiagram } from '@/components/docs/ArchitectureDiagram';
import { LiveMarketCard } from '@/components/docs/LiveMarketCard';

export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    ...components,
    InteractiveL2Sim,
    ContractAddress,
    ArchitectureDiagram,
    LiveMarketCard,
  };
}
