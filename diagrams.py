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