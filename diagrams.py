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
