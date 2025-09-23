# SimSXCu Backend Logic - Digital Twin Engine for Pyodide
# Version 6.0: Merged logic from Flask backend, including recommendation engine.
import numpy as np
from scipy.optimize import minimize
import json
import traceback

# --- CORE METALLURGICAL MODELS & CIRCUIT LOGIC ---
# Based on the principles for Lix984N.

def get_equilibrium_cu(aq_cu, aml):
    """
    Calculates the equilibrium copper concentration in the organic phase.
    This isotherm equation is a standard model for Lix984N behavior.
    """
    if aq_cu <= 0 or aml <= 0: return 0
    return (aml * aq_cu) / (2.5 + aq_cu)

def calculate_stage(aq_in_cu, org_in_cu, aml, oa_ratio, mixer_eff):
    """Simulates a single mixer-settler stage using an iterative approach to find equilibrium."""
    aq_out_cu, org_out_cu = max(0, aq_in_cu * 0.5), org_in_cu
    # Iteratively solve the mass balance equations until convergence
    for _ in range(25):
        org_eq_cu = get_equilibrium_cu(aq_out_cu, aml)
        org_out_cu_new = org_in_cu + (mixer_eff / 100.0) * (org_eq_cu - org_in_cu)
        aq_out_cu_new = aq_in_cu - (org_out_cu_new - org_in_cu) / oa_ratio

        if abs(aq_out_cu_new - aq_out_cu) < 1e-9 and abs(org_out_cu_new - org_out_cu) < 1e-9: break
        aq_out_cu, org_out_cu = aq_out_cu_new, org_out_cu_new # Corrected bug: was org_out_cu

    return max(0, aq_out_cu), max(0, org_out_cu)

def _circuit_series(inputs, so_cu, aml, oa_ratio_ext, num_stages):
    """Models a counter-current series circuit for extraction."""
    # Handle multiple PLS streams by creating a weighted average feed
    pls_streams = [(inputs.get(f'plsCu{i}', inputs.get('plsCu', 0)), inputs.get(f'plsFlow{i}', 0)) for i in range(1, 5)]
    # Use plsCu as default if specific streams are not present
    if all(flow == 0 for _, flow in pls_streams):
        pls_streams = [(inputs.get('plsCu', 0), 1)]

    total_cu_in = sum(cu * flow for cu, flow in pls_streams if flow > 0)
    total_flow = sum(flow for _, flow in pls_streams if flow > 0)
    avg_pls_cu = total_cu_in / total_flow if total_flow > 0 else 0

    org_outlets = [so_cu] * num_stages
    raff_temp = avg_pls_cu
    # Iterative loop to simulate the entire circuit until it stabilizes
    for _ in range(5):
        temp_aq_in_for_org_pass = avg_pls_cu
        for i in range(num_stages):
             mixer_eff = inputs.get(f'mef{i+1}e', 95)
             org_in = org_outlets[i-1] if i > 0 else so_cu
             _, org_outlets[i] = calculate_stage(temp_aq_in_for_org_pass, org_in, aml, oa_ratio_ext, mixer_eff)
             temp_aq_in_for_org_pass -= (org_outlets[i] - org_in) / oa_ratio_ext

        # This part of the loop in the original flask code was incorrect for a Pyodide context
        # The corrected logic from the original Pyodide version is more stable here.
        raff_temp = avg_pls_cu
        for i in range(num_stages - 1, -1, -1):
             org_in = org_outlets[i-1] if i > 0 else so_cu
             mixer_eff = inputs.get(f'mef{i+1}e', 95)
             aq_in_for_stage = avg_pls_cu - sum((org_outlets[j] - (org_outlets[j-1] if j > 0 else so_cu)) / oa_ratio_ext for j in range(i + 1, num_stages))
             raff_temp, _ = calculate_stage(aq_in_for_stage, org_in, aml, oa_ratio_ext, mixer_eff)

    return raff_temp, org_outlets[-1], avg_pls_cu

SCENARIO_CONFIG = {
    'A': {'strip_stages': 1, 'ext_stages': 2, 'circuit_logic': _circuit_series}, 'B': {'strip_stages': 2, 'ext_stages': 2, 'circuit_logic': _circuit_series},
    'C': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series}, 'D': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'E': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series}, 'F': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'G': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series}, 'H': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'I': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series}, 'J': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'K': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series}, 'L': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'M': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series}, 'N': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'O': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series}, 'P': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'Q': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series}, 'R': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
}

def _run_simulation(inputs, v_v, config):
    if v_v <= 0: return {'error': 'v/v% must be positive.'}
    aml = v_v * 0.517

    num_strip_stages = config.get('strip_stages', 1); ml_guess = aml * inputs.get('sr', 85) / 100
    temp_org_in = ml_guess
    for i in range(num_strip_stages, 0, -1):
        strip_eff = inputs.get(f'mef{i}s', 95)
        temp_org_in *= (1 - (strip_eff / 100.0) * 0.8)
    so_cu = max(0, temp_org_in)

    circuit_logic = config['circuit_logic']
    raffinate_cu, loaded_organic_cu, avg_pls_cu = circuit_logic(inputs, so_cu, aml, inputs.get('oaRatio', 1.0), config.get('ext_stages', 2))

    ml = loaded_organic_cu
    current_sr = (ml / aml) * 100 if aml > 0 else 0
    extraction_recovery = max(0, min(100, (avg_pls_cu - raffinate_cu) / avg_pls_cu * 100 if avg_pls_cu > 0 else 0))
    stripping_recovery = max(0, min(100, (ml - so_cu) / ml * 100 if ml > 0 else 0))
    net_transfer = (ml - so_cu) / v_v if v_v > 0 else 0

    return {
        'v_v': v_v, 'aml': aml, 'ml': ml, 'sr': current_sr, 'extraction_recovery': extraction_recovery,
        'stripping_recovery': stripping_recovery, 'net_transfer': net_transfer, 'raffinate_cu': raffinate_cu,
        'so_cu': so_cu, 'avg_pls_cu': avg_pls_cu
    }

def _run_sensitivity_analysis(base_inputs, base_results, v_v, config):
    recommendations = []
    params_to_test = {
        'oaRatio': {'name': 'نسبت O/A استخراج', 'delta': 0.05},
        'plsCu': {'name': 'غلظت PLS اصلی', 'delta': 0.05}
    }

    for param, info in params_to_test.items():
        if param not in base_inputs or base_inputs[param] == 0: continue

        perturbed_inputs = base_inputs.copy()
        change_factor = 1 + info['delta']
        perturbed_inputs[param] *= change_factor

        perturbed_results = _run_simulation(perturbed_inputs, v_v, config)
        if 'error' in perturbed_results: continue

        ext_rec_change = perturbed_results['extraction_recovery'] - base_results['extraction_recovery']

        if abs(ext_rec_change) > 0.1:
             sign = "افزایش" if ext_rec_change > 0 else "کاهش"
             recommendations.append(f"پیشنهاد: افزایش {info['delta']*100:.0f}٪ در '{info['name']}'، راندمان استخراج را حدود {abs(ext_rec_change):.2f}٪ {sign} می‌دهد.")

    if not recommendations:
        recommendations.append("فرآیند در حالت پایداری قرار دارد و به تغییرات کوچک در پارامترهای اصلی حساسیت کمی نشان می‌دهد.")

    return recommendations

def solver_for_v_v(inputs, config):
    target_sr = inputs.get('sr', 80)
    def objective_func(v_v_array):
        sim_results = _run_simulation(inputs, v_v_array[0], config)
        if 'error' in sim_results: return 1e9 # Return a large number if simulation fails
        return (sim_results['sr'] - target_sr) ** 2

    result = minimize(objective_func, [20.0], bounds=[(1, 100)], method='L-BFGS-B', tol=1e-9)
    return result.x[0] if result.success else float('nan')

def run_simulation_from_js(data_json):
    try:
        data = json.loads(data_json)
        inputs = {k: float(v) for k, v in data.get('inputs').items() if v is not None}
        scenario = data.get('scenario')
        option = data.get('option')

        config = SCENARIO_CONFIG.get(scenario)
        if not config: return {'error': f"Scenario {scenario} not implemented"}

        v_v_to_use = 0
        if option == '1': # Optimization mode
            optimal_v_v = solver_for_v_v(inputs, config)
            if np.isnan(optimal_v_v): return {'error': 'Solver failed to converge. Please check input parameters.'}
            v_v_to_use = optimal_v_v
        else: # Analysis mode
            v_v_to_use = inputs.get('v_v', 0)

        final_results = _run_simulation(inputs, v_v_to_use, config)
        if 'error' in final_results: return final_results

        recommendations = _run_sensitivity_analysis(inputs, final_results, v_v_to_use, config)

        return {
            'results': [
                {'label': 'درصد حجمی بهینه (v/v%)', 'value': f"{final_results['v_v']:.2f}", 'unit': '%'},
                {'label': 'حداکثر ظرفیت (AML)', 'value': f"{final_results['aml']:.2f}", 'unit': 'g/L'},
                {'label': 'فاز آلی باردار (ML)', 'value': f"{final_results['ml']:.2f}", 'unit': 'g/L'},
                {'label': 'راندمان استخراج', 'value': f"{final_results['extraction_recovery']:.2f}", 'unit': '%'},
                {'label': 'راندمان بازیافت', 'value': f"{final_results['stripping_recovery']:.2f}", 'unit': '%'},
                {'label': 'انتقال خالص', 'value': f"{final_results['net_transfer']:.3f}", 'unit': 'g/L/%'},
            ],
            'chartData': {
                'eq_x': list(np.linspace(0, final_results['avg_pls_cu'] * 1.1, 30)),
                'eq_y': [get_equilibrium_cu(x, final_results['aml']) for x in np.linspace(0, final_results['avg_pls_cu'] * 1.1, 30)],
                'op_x': [final_results['raffinate_cu'], final_results['avg_pls_cu']],
                'op_y': [final_results['so_cu'], final_results['ml']]
            },
            'recommendations': recommendations
        }
    except Exception as e:
        traceback.print_exc()
        return {'error': f'An unexpected error occurred in the Python backend: {str(e)}'}
