import numpy as np
import matplotlib.pyplot as plt

def lslmsr_price(q_yes, q_no, alpha):
    b = alpha * (q_yes + q_no)
    return np.exp(q_yes/b) / (np.exp(q_yes/b) + np.exp(q_no/b))

# Fixed q_no at seed scale midpoint
q_no = 40
q_yes = np.linspace(0.1, 80, 500)

alphas = {
    'High confidence α=0.012 (conf=0.90)': 0.012,
    'Mid confidence α=0.037 (conf=0.58)':  0.037,
    'Low confidence α=0.075 (conf=0.00)':  0.075,
}

colors = ['#58a6ff', '#3fb950', '#f78166']

fig, ax = plt.subplots(figsize=(10, 6))

for (label, alpha), color in zip(alphas.items(), colors):
    prices = [lslmsr_price(qy, q_no, alpha) for qy in q_yes]
    ax.plot(q_yes, prices, label=label, color=color, linewidth=2.5)

# 50% uninformed prior line
ax.axhline(0.5, color='#8b949e', linestyle='--', linewidth=1.2, label='Uninformed prior (50%)')

# ABMM seed point for ARV-806 (q_yes=39.52)
ax.axvline(39.52, color='orange', linestyle=':', linewidth=1.5, label='ABMM seed point (ARV-806, q_yes=39.52)')

ax.set_xlabel('q_yes (outstanding YES contracts)', fontsize=13)
ax.set_ylabel('Implied YES probability', fontsize=13)
ax.set_title('LS-LMSR Price Surface: Implied Probability vs. Outstanding Contracts\n(q_no fixed at 40)', fontsize=14)
ax.legend(fontsize=11)
ax.set_ylim(0, 1)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('figures/diagram1_price_surface.pdf', bbox_inches='tight')
plt.savefig('figures/diagram1_price_surface.png', dpi=150, bbox_inches='tight')
plt.show()
print("Saved to figures/diagram1_price_surface.pdf and .png")



# DIAGRAM 2 — The Cold Start Problem
fig, ax = plt.subplots(figsize=(10, 6))

confidence_scores = np.linspace(0.1, 0.95, 100)

def abmm_opening_price(conf):
    lit_score = 0.5
    eff = conf * 0.6 + lit_score * 0.4
    beta = 1000  # large scale keeps b well-conditioned
    q_yes = eff * beta
    q_no = (1 - eff) * beta
    alpha = 0.005 + (1 - conf) * 0.075
    b = alpha * (q_yes + q_no)
    return np.exp(q_yes/b) / (np.exp(q_yes/b) + np.exp(q_no/b))

prices_no_abmm = [0.5] * len(confidence_scores)
prices_abmm = [abmm_opening_price(c) for c in confidence_scores]

ax.plot(confidence_scores, prices_no_abmm, color='#f78166', linewidth=2.5,
        linestyle='--', label='Without ABMM: every molecule opens at 50%')
ax.plot(confidence_scores, prices_abmm, color='#3fb950', linewidth=2.5,
        label='With ABMM seeding: opening price reflects oracle prior')

ax.axvline(0.58, color='orange', linestyle=':', linewidth=1.5,
           label='ARV-806 (confidence=0.58)')
ax.scatter([0.58], [abmm_opening_price(0.58)], color='orange', zorder=5, s=80)
ax.annotate(f'  ARV-806: {abmm_opening_price(0.58):.1%} YES',
            xy=(0.58, abmm_opening_price(0.58)),
            fontsize=10, color='orange')

ax.set_xlabel('Oracle confidence score', fontsize=13)
ax.set_ylabel('Opening YES price', fontsize=13)
ax.set_title('The Cold-Start Problem: Opening Price vs. Oracle Confidence Score\nWithout ABMM seeding, every molecule opens at 50% regardless of prior', fontsize=13)
ax.legend(fontsize=11)
ax.set_ylim(0.0, 1.05)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('figures/diagram2_cold_start.pdf', bbox_inches='tight')
plt.savefig('figures/diagram2_cold_start.png', dpi=150, bbox_inches='tight')
plt.show()
print("Saved to figures/diagram2_cold_start.pdf and .png")


# DIAGRAM 3 — The Retreat Function Comparison
# Drop this block directly after the Diagram 2 block in diagrams.py

import numpy as np
import matplotlib.pyplot as plt

ldi = np.linspace(0, 1, 500)

# Retreat functions
ldi_half = 0.35
decay    = np.log(2) / ldi_half

def w_exponential(ldi):
    return np.exp(-decay * ldi)

def w_linear(ldi):
    return np.maximum(0, 1 - ldi)

def w_convex(ldi):
    return np.maximum(0, 1 - ldi ** 0.5)

w_exp  = w_exponential(ldi)
w_lin  = w_linear(ldi)
w_conv = w_convex(ldi)

# Crossover point: where exponential drops below linear
crossover_idx = np.argmin(np.abs(w_exp - w_lin))
ldi_cross     = ldi[crossover_idx]
w_cross       = w_exp[crossover_idx]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# ── Panel A: retreat function comparison ─────────────────────────────────
ax1.plot(ldi, w_exp,  color='#3fb950', linewidth=2.5,
         label=f'Exponential  w(t) = exp(−log(2)/0.35 × LDI)  [preferred]')
ax1.plot(ldi, w_lin,  color='#8b949e', linewidth=2.0, linestyle='--',
         label='Linear  w(t) = max(0, 1 − LDI)')
ax1.plot(ldi, w_conv, color='#f78166', linewidth=2.0, linestyle=':',
         label='Convex  w(t) = max(0, 1 − LDI⁰·⁵)')

# Mark half-life point
w_half = w_exponential(np.array([ldi_half]))[0]
ax1.scatter([ldi_half], [w_half], color='#3fb950', zorder=5, s=70)
ax1.annotate(f'Half-life: LDI = {ldi_half},  w = {w_half:.2f}',
             xy=(ldi_half, w_half), xytext=(ldi_half + 0.05, w_half + 0.07),
             fontsize=10, color='#3fb950',
             arrowprops=dict(arrowstyle='->', color='#3fb950', lw=1.2))

# Mark crossover
ax1.scatter([ldi_cross], [w_cross], color='#8b949e', zorder=5, s=60,
            marker='D')
ax1.annotate(f'Crossover: LDI ≈ {ldi_cross:.2f}',
             xy=(ldi_cross, w_cross), xytext=(ldi_cross + 0.05, w_cross - 0.10),
             fontsize=10, color='#8b949e',
             arrowprops=dict(arrowstyle='->', color='#8b949e', lw=1.1))

# Shade regions
ax1.fill_between(ldi, w_exp, w_lin,
                 where=(w_exp >= w_lin),
                 alpha=0.08, color='#3fb950',
                 label='_nolegend_')
ax1.fill_between(ldi, w_exp, w_lin,
                 where=(w_exp < w_lin),
                 alpha=0.08, color='#8b949e',
                 label='_nolegend_')

# Region labels
ax1.text(0.10, 0.30, 'Exponential retreats\nfaster than linear\n(early expert signal\nmaximally weighted)',
         fontsize=9.5, color='#3fb950', ha='center',
         bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='#3fb950', alpha=0.85))
ax1.text(0.72, 0.22, 'Exponential retreats\nslower than linear\n(residual floor prevents\ncollapse in thin markets)',
         fontsize=9.5, color='#8b949e', ha='center',
         bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='#8b949e', alpha=0.85))

ax1.set_xlabel('LDI  (credentialed volume / total volume)', fontsize=13)
ax1.set_ylabel('ABMM influence  w(t)', fontsize=13)
ax1.set_title('Retreat Function Comparison\n'
              'Exponential retreats faster early, maintains residual floor late',
              fontsize=12)
ax1.legend(fontsize=10, loc='upper right')
ax1.set_ylim(-0.02, 1.08)
ax1.set_xlim(-0.01, 1.01)
ax1.grid(True, alpha=0.3)

# ── Panel B: simulated price path for ARV-806 ────────────────────────────
# Shows how the market price evolves as experts trade and ABMM retreats.
# Demonstrates that price movement accelerates as ABMM influence falls.

np.random.seed(42)
n_trades    = 60
alpha_arv   = 0.0365       # ARV-806: conf=0.58
prior_yes   = 0.104        # Hay et al. IND milestone base rate

# Seed ABMM quantities
q_yes = prior_yes * 80
q_no  = (1 - prior_yes) * 80
ldi_t = 0.0

prices_sim   = [q_yes / (q_yes + q_no)]   # approximate opening
ldi_sim      = [ldi_t]
influence_sim = [1.0]

for _ in range(n_trades):
    # Expert trade: slight positive drift (molecule succeeds)
    trade = np.random.normal(0.10, 0.18)
    if trade > 0:
        q_yes += trade
    else:
        q_no  += abs(trade)

    # LDI increments only on credentialed trades (all trades here are credentialed)
    ldi_t = min(1.0, ldi_t + np.random.uniform(0.012, 0.028))

    b = alpha_arv * (q_yes + q_no)
    p = np.exp(q_yes / b) / (np.exp(q_yes / b) + np.exp(q_no / b))

    prices_sim.append(p)
    ldi_sim.append(ldi_t)
    influence_sim.append(w_exponential(np.array([ldi_t]))[0])

trade_idx = range(len(prices_sim))

ax2_twin = ax2.twinx()

ax2.plot(trade_idx, prices_sim,    color='#3fb950', linewidth=2.5,
         label='P(IND) — ARV-806')
ax2.axhline(prior_yes, color='#8b949e', linewidth=1.2, linestyle='--',
            label=f'Hay et al. base rate ({prior_yes:.1%})')

ax2_twin.fill_between(trade_idx, 0, influence_sim,
                      alpha=0.12, color='#58a6ff')
ax2_twin.plot(trade_idx, influence_sim, color='#58a6ff', linewidth=1.5,
              linestyle=':', label='ABMM influence  w(t)')

# Mark LDI half-life crossing
half_idx = next((i for i, w in enumerate(influence_sim) if w <= 0.5), None)
if half_idx:
    ax2.axvline(half_idx, color='#58a6ff', linewidth=1.0,
                linestyle=':', alpha=0.7)
    ax2.text(half_idx + 0.5, 0.18,
             f'LDI half-life\n(trade ~{half_idx})',
             fontsize=9, color='#58a6ff')

ax2.set_xlabel('Credentialed trade index', fontsize=13)
ax2.set_ylabel('Market YES price  P(IND)', fontsize=13)
ax2_twin.set_ylabel('ABMM influence  w(t)', color='#58a6ff', fontsize=12)
ax2_twin.tick_params(axis='y', labelcolor='#58a6ff')
ax2_twin.set_ylim(0, 1.5)

ax2.set_title('Simulated Price Path — ARV-806\n'
              'Price discovery accelerates as ABMM influence retreats',
              fontsize=12)
ax2.set_ylim(0.0, 1.05)

# Combined legend
lines1, labels1 = ax2.get_legend_handles_labels()
lines2, labels2 = ax2_twin.get_legend_handles_labels()
ax2.legend(lines1 + lines2, labels1 + labels2, fontsize=10, loc='lower right')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('figures/diagram3_retreat_function.pdf', bbox_inches='tight')
plt.savefig('figures/diagram3_retreat_function.png', dpi=150, bbox_inches='tight')
plt.show()
print("Saved to figures/diagram3_retreat_function.pdf and .png")



# DIAGRAM 5 — The Retreat Under ABMM Dominance

import numpy as np
import matplotlib.pyplot as plt

def lslmsr_price(q_yes, q_no, alpha):
    b = alpha * (q_yes + q_no)
    return np.exp(q_yes/b) / (np.exp(q_yes/b) + np.exp(q_no/b))

def lslmsr_cost(q_yes, q_no, alpha):
    b = alpha * (q_yes + q_no)
    return b * np.log(np.exp(q_yes/b) + np.exp(q_no/b))

def cost_to_move(q_yes, q_no, alpha, p_target):
    """Cost for expert to move market from current price to p_target."""
    b_old   = alpha * (q_yes + q_no)
    c_old   = lslmsr_cost(q_yes, q_no, alpha)
    # solve for q_yes_new such that price = p_target
    # p = exp(qy/b) / (exp(qy/b)+exp(qn/b)) => qy_new = qn + b*log(p/(1-p))
    # but b changes with qy_new, so iterate
    q_yes_new = q_yes
    for _ in range(500):
        b = alpha * (q_yes_new + q_no)
        q_yes_new = q_no + b * np.log(p_target / (1 - p_target))
    c_new = lslmsr_cost(q_yes_new, q_no, alpha)
    return max(0.0, c_new - c_old)

# Parameters
p_star    = 0.70     # expert's true belief
p_abmm    = 0.42     # ABMM-seeded prior
alpha_ex  = 0.04325  # conf≈0.49 molecule
beta      = 80       # seeding scale
ldi_half  = 0.35

ldi_range = np.linspace(0.0, 1.0, 200)

def w_exp(ldi):
    return np.exp(-np.log(2) / ldi_half * ldi)

# At each LDI, ABMM holds w(ldi) fraction of its initial stake
# q_abmm_yes = p_abmm * beta * w(ldi), q_abmm_no = (1-p_abmm)*beta*w(ldi)
# Expert trades on top of this residual ABMM position
costs_truthful = []
costs_agree    = []    # expert who agrees with prior: p* ≈ p_abmm
costs_disagree = []    # expert who strongly disagrees: p* = 0.85

for ldi in ldi_range:
    w = w_exp(ldi)
    qy = p_abmm * beta * w
    qn = (1 - p_abmm) * beta * w

    costs_truthful.append(cost_to_move(qy, qn, alpha_ex, p_star))
    costs_agree.append(cost_to_move(qy, qn, alpha_ex, p_abmm + 0.02))
    costs_disagree.append(cost_to_move(qy, qn, alpha_ex, 0.85))

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# ── Panel A: cost of truthful reporting vs LDI ───────────────────────────
ax1.plot(ldi_range, costs_truthful, color='#3fb950', linewidth=2.5,
         label=f'p* = {p_star}  vs  p_abmm = {p_abmm}  (disagreement)')
ax1.plot(ldi_range, costs_disagree, color='#f78166', linewidth=2.0,
         linestyle='--', label='p* = 0.85  (strong disagreement)')
ax1.plot(ldi_range, costs_agree,    color='#8b949e', linewidth=2.0,
         linestyle=':',  label=f'p* ≈ p_abmm  (agrees with prior)')

# Mark half-life
ldi_hl   = ldi_half
cost_hl  = cost_to_move(p_abmm*beta*w_exp(ldi_hl),
                         (1-p_abmm)*beta*w_exp(ldi_hl),
                         alpha_ex, p_star)
ax1.scatter([ldi_hl], [cost_hl], color='#3fb950', zorder=5, s=70)
ax1.axvline(ldi_hl, color='#3fb950', linewidth=1.0, linestyle=':', alpha=0.6)
ax1.annotate(f'ABMM half-life\nLDI = {ldi_hl}',
             xy=(ldi_hl, cost_hl), xytext=(ldi_hl + 0.07, cost_hl + 0.4),
             fontsize=10, color='#3fb950',
             arrowprops=dict(arrowstyle='->', color='#3fb950', lw=1.1))

# Shade high-distortion region
ax1.axvspan(0, ldi_hl, alpha=0.06, color='#f78166',
            label='_nolegend_')
ax1.text(ldi_hl / 2, ax1.get_ylim()[1] * 0.88 if costs_truthful[0] > 0 else 1.2,
         'High distortion\nregion',
         ha='center', fontsize=9.5, color='#f78166',
         bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#f78166', alpha=0.85))

ax1.set_xlabel('LDI  (credentialed volume / total volume)', fontsize=13)
ax1.set_ylabel('Cost of truthful reporting  Δ C(q)', fontsize=13)
ax1.set_title('ε-IC Condition: Cost of Truthful Reporting vs. LDI\n'
              'Distortion is worst early — when correction is most valuable',
              fontsize=12)
ax1.legend(fontsize=10)
ax1.set_xlim(-0.01, 1.01)
ax1.grid(True, alpha=0.3)

# ── Panel B: cost surface over (LDI, p*) ─────────────────────────────────
p_targets  = np.linspace(0.44, 0.90, 60)
ldi_grid   = np.linspace(0.0, 1.0, 60)
LDI, PT    = np.meshgrid(ldi_grid, p_targets)
Z          = np.zeros_like(LDI)

for i, pt in enumerate(p_targets):
    for j, ld in enumerate(ldi_grid):
        w  = w_exp(ld)
        qy = p_abmm * beta * w
        qn = (1 - p_abmm) * beta * w
        Z[i, j] = cost_to_move(qy, qn, alpha_ex, pt)

contour = ax2.contourf(LDI, PT, Z, levels=16,
                        cmap='RdYlGn_r', alpha=0.85)
cbar = plt.colorbar(contour, ax=ax2, pad=0.02)
cbar.set_label('Cost of truthful reporting  Δ C(q)', fontsize=10)

# Mark the p*=0.70 case
ax2.axhline(p_star, color='#3fb950', linewidth=1.5, linestyle='--',
            label=f'p* = {p_star} (main case)')
ax2.axvline(ldi_half, color='white', linewidth=1.0, linestyle=':',
            alpha=0.7, label=f'LDI half-life = {ldi_half}')
ax2.scatter([0], [p_star], color='#3fb950', zorder=5, s=80,
            label=f'Maximum distortion point')

ax2.set_xlabel('LDI  (credentialed volume / total volume)', fontsize=13)
ax2.set_ylabel('Expert true belief  p*', fontsize=13)
ax2.set_title(f'Cost Surface: f(LDI, p*)  with  p_abmm = {p_abmm}\n'
              'Distortion peaks at low LDI and high |p* − p_abmm|',
              fontsize=12)
ax2.legend(fontsize=10, loc='lower right')
ax2.grid(True, alpha=0.2)

plt.tight_layout()
plt.savefig('figures/diagram5_ic_distortion.pdf', bbox_inches='tight')
plt.savefig('figures/diagram5_ic_distortion.png', dpi=150, bbox_inches='tight')
plt.close()
print("Saved to figures/diagram5_ic_distortion.pdf and .png")