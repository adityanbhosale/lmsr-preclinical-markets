'use client';

import { useState, useMemo } from 'react';
import {
  useAccount,
  useReadContract,
  useWriteContract,
  useWaitForTransactionReceipt,
} from 'wagmi';
import { parseUnits } from 'viem';
import { CONTRACTS } from '@/lib/contracts';
import { lslmsrAbi } from '@/lib/abi/lslmsr';
import { erc20Abi } from '@/lib/abi/usdc';
import { formatUsdcNumber, formatUsdc } from '@/lib/format';

type Side = 'yes' | 'no';
type FlowStep = 'idle' | 'approving' | 'awaiting_approve' | 'trading' | 'awaiting_trade';

export interface TradeFormProps {
  marketAddress: `0x${string}`;
}

/**
 * TradeForm — buy YES or NO shares.
 *
 * Flow:
 *   1. User picks YES/NO, types share count
 *   2. Cost preview computes via costOfTrade() — updates as input changes
 *   3. On submit, frontend checks allowance:
 *      - If insufficient, prompt user to approve USDC → wait for confirmation
 *      - Then prompt user to trade → wait for confirmation
 *   4. After confirmation, form resets and parent re-fetches state
 *
 * The single button progresses through labels ("Approve & buy YES" →
 * "Approving..." → "Submitting trade..." → "Done") so user sees one
 * cognitive action even though it's two transactions on first trade.
 *
 * Future improvement: contract-side `tradeWithPermit` would collapse
 * this to a single signature. Documented but not implemented.
 */
export function TradeForm({ marketAddress }: TradeFormProps) {
  const { address, isConnected, chain } = useAccount();
  const onCorrectChain = chain?.id === CONTRACTS.lslmsr.chainId;

  // Form state
  const [side, setSide] = useState<Side>('yes');
  const [sharesInput, setSharesInput] = useState<string>('1');
  const [step, setStep] = useState<FlowStep>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Parse shares input → UD60x18 BigInt (18 decimals)
  // Returns 0n if input is invalid/empty
  const sharesAsUD60x18 = useMemo(() => {
    if (!sharesInput || isNaN(parseFloat(sharesInput))) return 0n;
    try {
      return parseUnits(sharesInput, 18);
    } catch {
      return 0n;
    }
  }, [sharesInput]);

  // Read live cost preview from contract
  const { data: costUD60x18 } = useReadContract({
    address: marketAddress,
    abi: lslmsrAbi,
    chainId: CONTRACTS.lslmsr.chainId,
    functionName: 'costOfTrade',
    args: [side === 'yes', sharesAsUD60x18],
    query: {
      enabled: sharesAsUD60x18 > 0n,
      refetchInterval: 12_000,
    },
  });

  // Convert UD60x18 cost → USDC 6-decimal cost
  const costUSDC = useMemo(() => {
    if (!costUD60x18) return 0n;
    return costUD60x18 / 10n ** 12n; // UD60x18 → 6-decimal
  }, [costUD60x18]);

  // Read current allowance to decide whether approve is needed
  const { data: allowance, refetch: refetchAllowance } = useReadContract({
    address: CONTRACTS.usdc.address,
    abi: erc20Abi,
    chainId: CONTRACTS.usdc.chainId,
    functionName: 'allowance',
    args: address ? [address, marketAddress] : undefined,
    query: {
      enabled: !!address,
      refetchInterval: 12_000,
    },
  });

  const needsApproval = useMemo(() => {
    if (!costUSDC || costUSDC === 0n) return false;
    if (allowance === undefined) return true;
    return allowance < costUSDC;
  }, [costUSDC, allowance]);

  // Write hooks
  const {
    writeContract: writeApprove,
    data: approveTxHash,
    error: approveError,
    reset: resetApprove,
  } = useWriteContract();
  const { isLoading: approveConfirming, isSuccess: approveConfirmed } =
    useWaitForTransactionReceipt({
      hash: approveTxHash,
    });

  const {
    writeContract: writeTrade,
    data: tradeTxHash,
    error: tradeError,
    reset: resetTrade,
  } = useWriteContract();
  const { isLoading: tradeConfirming, isSuccess: tradeConfirmed } =
    useWaitForTransactionReceipt({
      hash: tradeTxHash,
    });

  // ─────────────────────────────────────────────────────────────
  // Flow orchestration via effects
  // ─────────────────────────────────────────────────────────────

  // After approve confirms, refetch allowance and trigger trade
  if (approveConfirmed && step === 'awaiting_approve') {
    refetchAllowance();
    setStep('trading');
    writeTrade({
      address: marketAddress,
      abi: lslmsrAbi,
      chainId: CONTRACTS.lslmsr.chainId,
      functionName: 'trade',
      args: [side === 'yes', sharesAsUD60x18],
    });
    setStep('awaiting_trade');
  }

  // After trade confirms, reset
  if (tradeConfirmed && step === 'awaiting_trade') {
    setStep('idle');
    resetApprove();
    resetTrade();
    setSharesInput('1');
  }

  // Handle errors mid-flow
  if (approveError && step !== 'idle') {
    setErrorMsg(`Approval failed: ${approveError.message.slice(0, 80)}`);
    setStep('idle');
    resetApprove();
  }
  if (tradeError && step !== 'idle') {
    setErrorMsg(`Trade failed: ${tradeError.message.slice(0, 80)}`);
    setStep('idle');
    resetTrade();
  }

  // ─────────────────────────────────────────────────────────────
  // Submit handler
  // ─────────────────────────────────────────────────────────────

  function handleSubmit() {
    setErrorMsg(null);
    if (!address || !sharesAsUD60x18 || sharesAsUD60x18 === 0n) return;

    if (needsApproval) {
      setStep('approving');
      writeApprove({
        address: CONTRACTS.usdc.address,
        abi: erc20Abi,
        chainId: CONTRACTS.usdc.chainId,
        functionName: 'approve',
        args: [marketAddress, costUSDC + 10n ** 6n], // a touch of slack
      });
      setStep('awaiting_approve');
    } else {
      setStep('trading');
      writeTrade({
        address: marketAddress,
        abi: lslmsrAbi,
        chainId: CONTRACTS.lslmsr.chainId,
        functionName: 'trade',
        args: [side === 'yes', sharesAsUD60x18],
      });
      setStep('awaiting_trade');
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────

  if (!isConnected) {
    return (
      <section className="border border-dashed border-border rounded-lg p-6 text-xs text-muted-foreground">
        Connect a wallet to trade against the market.
      </section>
    );
  }

  if (!onCorrectChain) {
    return (
      <section className="border border-orange-200 bg-orange-50 rounded-lg p-4 text-xs">
        <span className="font-semibold text-orange-900">
          Switch to Base Sepolia
        </span>
        <p className="text-orange-700 mt-1">
          Trades happen on Base Sepolia (chain 84532). Switch networks in
          your wallet to continue.
        </p>
      </section>
    );
  }

  const buttonLabel = (() => {
    if (step === 'awaiting_approve' || (step === 'approving' && !approveConfirming))
      return 'Confirm approval in wallet...';
    if (approveConfirming) return 'Approving USDC...';
    if (step === 'awaiting_trade' || step === 'trading')
      return tradeConfirming ? 'Submitting trade...' : 'Confirm trade in wallet...';
    if (needsApproval) return `Approve & buy ${side.toUpperCase()}`;
    return `Buy ${side.toUpperCase()}`;
  })();

  const buttonDisabled =
    step !== 'idle' ||
    sharesAsUD60x18 === 0n ||
    !costUSDC ||
    costUSDC === 0n;

  return (
    <section className="border border-border rounded-lg p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold tracking-tight">Trade</h3>
        <span className="text-xs text-muted-foreground">on Base Sepolia</span>
      </div>

      {/* Side toggle */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setSide('yes')}
          disabled={step !== 'idle'}
          className={`py-2 px-3 rounded text-sm font-semibold transition-colors ${
            side === 'yes'
              ? 'bg-green-600 text-white'
              : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          YES
        </button>
        <button
          type="button"
          onClick={() => setSide('no')}
          disabled={step !== 'idle'}
          className={`py-2 px-3 rounded text-sm font-semibold transition-colors ${
            side === 'no'
              ? 'bg-red-600 text-white'
              : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          NO
        </button>
      </div>

      {/* Shares input */}
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground" htmlFor="shares">
          Shares to buy
        </label>
        <input
          id="shares"
          type="number"
          min="0"
          step="0.1"
          value={sharesInput}
          onChange={(e) => setSharesInput(e.target.value)}
          disabled={step !== 'idle'}
          className="w-full px-3 py-2 border border-border rounded font-mono tabular-nums text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
      </div>

      {/* Cost preview */}
      <div className="bg-muted rounded p-3 space-y-1 text-xs">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Cost:</span>
          <span className="font-mono tabular-nums font-semibold">
            {costUSDC > 0n ? formatUsdc(costUSDC) : '$0.00'}
          </span>
        </div>
        {sharesAsUD60x18 > 0n && costUSDC > 0n && (
          <div className="flex justify-between text-muted-foreground/70">
            <span>Avg price per share:</span>
            <span className="font-mono tabular-nums">
              {formatUsdc(
                (costUSDC * 10n ** 18n) / sharesAsUD60x18,
                4
              )}
            </span>
          </div>
        )}
      </div>

      {/* Error display */}
      {errorMsg && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-xs text-red-700">
          {errorMsg}
        </div>
      )}

      {/* Submit button */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={buttonDisabled}
        className="w-full py-2.5 px-4 bg-primary text-primary-foreground rounded text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {buttonLabel}
      </button>

      {/* Tx hash links during/after flow */}
      {(approveTxHash || tradeTxHash) && (
        <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t border-border">
          {approveTxHash && (
            <div>
              Approval tx:{' '}
              <a
                href={`${CONTRACTS.lslmsr.explorer}/tx/${approveTxHash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono hover:text-foreground underline-offset-2 hover:underline"
              >
                {approveTxHash.slice(0, 10)}...{approveTxHash.slice(-8)}
              </a>
              {approveConfirmed && ' ✓'}
            </div>
          )}
          {tradeTxHash && (
            <div>
              Trade tx:{' '}
              <a
                href={`${CONTRACTS.lslmsr.explorer}/tx/${tradeTxHash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono hover:text-foreground underline-offset-2 hover:underline"
              >
                {tradeTxHash.slice(0, 10)}...{tradeTxHash.slice(-8)}
              </a>
              {tradeConfirmed && ' ✓'}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
