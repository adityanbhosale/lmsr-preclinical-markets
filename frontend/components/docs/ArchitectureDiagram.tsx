/**
 * <ArchitectureDiagram /> — SVG of the dual-layer split.
 *
 * Two stacked panels (Layer 1, Layer 2) with the CCTP bridge connecting
 * them and the off-chain Outcome Resolver feeding both. Uses currentColor
 * so it inherits the page text color cleanly.
 */

export function ArchitectureDiagram() {
  return (
    <figure className="not-prose my-8 rounded-lg border border-neutral-200 bg-white p-6">
      <svg
        viewBox="0 0 720 460"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-auto text-neutral-900"
        role="img"
        aria-labelledby="architecture-diagram-title"
      >
        <title id="architecture-diagram-title">
          Dual-layer architecture: ERC-3643 SPV on Ethereum (Layer 1), LS-LMSR event
          contract on Base (Layer 2), connected via Circle CCTP.
        </title>

        <defs>
          <marker
            id="arrowhead"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M2 1 L8 5 L2 9 Z" fill="currentColor" stroke="none" />
          </marker>
        </defs>

        {/* Layer 1 panel */}
        <g>
          <rect
            x="40"
            y="30"
            width="640"
            height="130"
            rx="8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.25"
            opacity="0.9"
          />
          <text
            x="60"
            y="58"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize="11"
            fontWeight="600"
            letterSpacing="0.08em"
            fill="currentColor"
            opacity="0.55"
          >
            LAYER 1 · ETHEREUM SEPOLIA
          </text>
          <text
            x="60"
            y="86"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="20"
            fontWeight="600"
            fill="currentColor"
          >
            ERC-3643 SPV
          </text>
          <text
            x="60"
            y="110"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="13"
            fill="currentColor"
            opacity="0.75"
          >
            Identity Registry · Compliance Module · Milestone Tokens
          </text>
          <text
            x="60"
            y="132"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="12"
            fill="currentColor"
            opacity="0.6"
            fontStyle="italic"
          >
            Permissioned · Identity-gated · Reg D 506(c) transfer restrictions
          </text>
          <text
            x="660"
            y="148"
            textAnchor="end"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize="10"
            fill="currentColor"
            opacity="0.5"
          >
            Holds the legal claim
          </text>
        </g>

        {/* CCTP bridge */}
        <g>
          <line
            x1="360"
            y1="160"
            x2="360"
            y2="200"
            stroke="currentColor"
            strokeWidth="1.25"
            strokeDasharray="3 3"
            markerEnd="url(#arrowhead)"
            opacity="0.7"
          />
          <line
            x1="380"
            y1="200"
            x2="380"
            y2="160"
            stroke="currentColor"
            strokeWidth="1.25"
            strokeDasharray="3 3"
            markerEnd="url(#arrowhead)"
            opacity="0.7"
          />
          <rect
            x="240"
            y="170"
            width="260"
            height="34"
            rx="17"
            fill="white"
            stroke="currentColor"
            strokeWidth="1.25"
            opacity="0.95"
          />
          <text
            x="370"
            y="192"
            textAnchor="middle"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize="11"
            fontWeight="600"
            fill="currentColor"
          >
            Circle CCTP · Native USDC · No wrapped bridge
          </text>
        </g>

        {/* Layer 2 panel */}
        <g>
          <rect
            x="40"
            y="220"
            width="640"
            height="130"
            rx="8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.25"
            opacity="0.9"
          />
          <text
            x="60"
            y="248"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize="11"
            fontWeight="600"
            letterSpacing="0.08em"
            fill="currentColor"
            opacity="0.55"
          >
            LAYER 2 · BASE SEPOLIA
          </text>
          <text
            x="60"
            y="276"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="20"
            fontWeight="600"
            fill="currentColor"
          >
            LS-LMSR Event Contract
          </text>
          <text
            x="60"
            y="300"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="13"
            fill="currentColor"
            opacity="0.75"
          >
            ABMM seeding · Liquidity-sensitive b(q) · USDC settlement
          </text>
          <text
            x="60"
            y="322"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="12"
            fill="currentColor"
            opacity="0.6"
            fontStyle="italic"
          >
            Permissionless · Continuous price discovery · Public outcome reference
          </text>
          <text
            x="660"
            y="338"
            textAnchor="end"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize="10"
            fill="currentColor"
            opacity="0.5"
          >
            Discovers the price
          </text>
        </g>

        {/* Outcome Resolver */}
        <g>
          <line
            x1="360"
            y1="350"
            x2="360"
            y2="395"
            stroke="currentColor"
            strokeWidth="1.25"
            strokeDasharray="2 4"
            markerStart="url(#arrowhead)"
            opacity="0.5"
          />
          <rect
            x="220"
            y="395"
            width="280"
            height="44"
            rx="6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.25"
            strokeDasharray="4 3"
            opacity="0.6"
          />
          <text
            x="360"
            y="416"
            textAnchor="middle"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize="11"
            fontWeight="600"
            fill="currentColor"
            opacity="0.8"
          >
            Outcome Resolver (off-chain)
          </text>
          <text
            x="360"
            y="431"
            textAnchor="middle"
            fontFamily="system-ui, -apple-system, sans-serif"
            fontSize="10"
            fill="currentColor"
            opacity="0.55"
            fontStyle="italic"
          >
            Testnet: admin stub · Production: credentialed-DSMB
          </text>
        </g>
      </svg>
      <figcaption className="mt-3 text-center text-xs text-neutral-500">
        Dual-layer architecture. Layer 1 holds the regulated security; Layer 2 hosts
        permissionless price discovery; CCTP bridges native USDC across the boundary.
      </figcaption>
    </figure>
  );
}
