import numpy as np

print("=" * 60)
print("LS-LMSR Python vs Solidity Cross-Check")
print("=" * 60)

# Cross-check 1: Symmetric market, initial price
alpha = 0.05
q_yes = 100
q_no = 100

b = alpha * (q_yes + q_no)
exp_yes = np.exp(q_yes / b)
exp_no = np.exp(q_no / b)
price_yes_symmetric = exp_yes / (exp_yes + exp_no)

print(f"\n[1] Symmetric market (q_yes=100, q_no=100, alpha=0.05)")
print(f"    Python price:   {price_yes_symmetric:.18f}")
print(f"    Solidity price: 0.500000000000000000")
print(f"    Match: {abs(price_yes_symmetric - 0.5) < 1e-15}")

# Cross-check 2: Asymmetric seeding
q_yes = 150
q_no = 50

b = alpha * (q_yes + q_no)
exp_yes = np.exp(q_yes / b)
exp_no = np.exp(q_no / b)
price_yes_asymmetric = exp_yes / (exp_yes + exp_no)
solidity_price = 999954602131297565 / 1e18

print(f"\n[2] Asymmetric seeding (q_yes=150, q_no=50, alpha=0.05)")
print(f"    Python price:   {price_yes_asymmetric:.18f}")
print(f"    Solidity price: {solidity_price:.18f}")
print(f"    Difference:     {abs(price_yes_asymmetric - solidity_price):.2e}")

# Cross-check 3: After buying 10 YES shares
q_yes = 100
q_no = 100

b_before = alpha * (q_yes + q_no)
exp_yes_before = np.exp(q_yes / b_before)
exp_no_before = np.exp(q_no / b_before)
price_before = exp_yes_before / (exp_yes_before + exp_no_before)

q_yes_new = q_yes + 10
b_after = alpha * (q_yes_new + q_no)
exp_yes_after = np.exp(q_yes_new / b_after)
exp_no_after = np.exp(q_no / b_after)
price_after = exp_yes_after / (exp_yes_after + exp_no_after)

solidity_after = 721593754600356249 / 1e18

print(f"\n[3] Buy 10 YES shares against symmetric market")
print(f"    Python price after:   {price_after:.18f}")
print(f"    Solidity price after: {solidity_after:.18f}")
print(f"    Difference:           {abs(price_after - solidity_after):.2e}")

print("\n" + "=" * 60)