# SimSXCu Backend Logic - Exact Digital Twin Engine (for Pyodide)
# Version 4.0: Final version with one-to-one mapping of all Excel inputs.
import numpy as np
from scipy.optimize import minimize
import json

# --- CORE METALLURGICAL MODELS ---

def get_equilibrium_cu(aq_cu, aml):
    """Langmuir-type isotherm for Lix984N extractant."""
    if aq_cu <= 0 or aml <= 0: return 0
    return (aml * aq_cu) / (2.5 + aq_cu)

def calculate_stage(aq_in_cu, org_in_cu, aml, oa_ratio, mixer_eff):
    """Models a single counter-current mixer-settler stage with high precision."""
    aq_out_cu = max(0, aq_in_cu * 0.5)
    org_out_cu = org_in_cu
    for _ in range(25): # Increased iterations for stability
        org_eq_cu = get_equilibrium_cu(aq_out_cu, aml)
        org_out_cu_new = org_in_cu + (mixer_eff / 100.0) * (org_eq_cu - org_in_cu)
        aq_out_cu_new = aq_in_cu - (org_out_cu_new - org_in_cu) / oa_ratio

        # Convergence check
        if abs(aq_out_cu_new - aq_out_cu) < 1e-9 and abs(org_out_cu_new - org_out_cu) < 1e-9:
            break
        aq_out_cu = aq_out_cu_new
        org_out_cu = org_out_cu_new

    return max(0, aq_out_cu), max(0, org_out_cu)

# --- DETAILED CIRCUIT LOGIC ---

def _circuit_series(inputs, so_cu, aml, oa_ratio_ext, num_stages):
    """Simulates a generic counter-current series circuit using exact parameters."""
    aq_stream = inputs.get('plsCu', inputs.get('plsCu1', 0))

    org_outlets = [so_cu] * num_stages
    raff_temp = aq_stream
    for _ in range(5): # Outer loop to converge the whole circuit
        temp_aq_in_for_org_pass = aq_stream
        for i in range(num_stages):
             mixer_eff = inputs.get(f'mef{i+1}e', 95)
             org_in = org_outlets[i-1] if i > 0 else so_cu
             _, org_outlets[i] = calculate_stage(temp_aq_in_for_org_pass, org_in, aml, oa_ratio_ext, mixer_eff)
             temp_aq_in_for_org_pass -= (org_outlets[i] - org_in) / oa_ratio_ext

        raff_temp = aq_stream
        for i in range(num_stages - 1, -1, -1):
             org_in = org_outlets[i-1] if i > 0 else so_cu
             mixer_eff = inputs.get(f'mef{i+1}e', 95)
             raff_temp, _ = calculate_stage(raff_temp, org_in, aml, oa_ratio_ext, mixer_eff)

    return raff_temp, org_outlets[-1]

# --- MASTER SIMULATOR & CONFIGURATION ---

SCENARIO_CONFIG = {
    'A': {'strip_stages': 1, 'ext_stages': 2, 'circuit_logic': _circuit_series},
    'B': {'strip_stages': 2, 'ext_stages': 2, 'circuit_logic': _circuit_series},
    'C': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'D': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'E': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'F': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'G': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'H': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'I': {'strip_stages': 1, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'J': {'strip_stages': 2, 'ext_stages': 3, 'circuit_logic': _circuit_series},
    'K': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'L': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'M': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'N': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'O': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'P': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'Q': {'strip_stages': 1, 'ext_stages': 4, 'circuit_logic': _circuit_series},
    'R': {'strip_stages': 2, 'ext_stages': 4, 'circuit_logic': _circuit_series},
}

def _run_simulation(inputs, v_v, config):
    aml = v_v * 0.517

    num_strip_stages = config.get('strip_stages', 1)
    ml_guess = aml * inputs.get('sr', 85) / 100
    sp_cu = inputs.get('spCu', 35)
    oa_strip_ratio = inputs.get('oaRatioStrip', 1.0)

    temp_org_in = ml_guess
    for i in range(num_strip_stages, 0, -1):
        strip_eff = inputs.get(f'mef{i}s', 95)
        temp_org_in *= (1 - (strip_eff / 100.0) * 0.8)
    so_cu = max(0, temp_org_in)

    pls_streams = [(inputs[k], inputs.get(k.replace('Cu', 'Flow'), 1)) for k in inputs if k.startswith('plsCu')]
    if not pls_streams:
        return {'error': 'No PLS stream data found in inputs.'}

    total_cu_in = sum(cu * flow for cu, flow in pls_streams)
    total_flow = sum(flow for _, flow in pls_streams)
    avg_pls_cu = total_cu_in / total_flow if total_flow > 0 else 0

    unified_inputs = inputs.copy()
    unified_inputs['plsCu'] = avg_pls_cu

    circuit_logic = config['circuit_logic']
    raffinate_cu, loaded_organic_cu = circuit_logic(unified_inputs, so_cu, aml, inputs.get('oaRatio', 1.0), config.get('ext_stages', 2))

    ml = loaded_organic_cu
    current_sr = (ml / aml) * 100 if aml > 0 else 0

    extraction_recovery = max(0, min(100, (avg_pls_cu - raffinate_cu) / avg_pls_cu * 100 if avg_pls_cu > 0 else 0))
    stripping_recovery = max(0, min(100, (ml - so_cu) / ml * 100 if ml > 0 else 0))
    net_transfer = (ml - so_cu) / v_v if v_v > 0 else 0

    return {
        'v_v': v_v, 'aml': aml, 'ml': ml, 'sr': current_sr,
        'extraction_recovery': extraction_recovery, 'stripping_recovery': stripping_recovery,
        'net_transfer': net_transfer, 'raffinate_cu': raffinate_cu, 'so_cu': so_cu, 'avg_pls_cu': avg_pls_cu
    }

# --- SOLVER & MAIN ENTRY POINT ---
def solver_for_v_v(inputs, config):
    target_sr = inputs.get('sr', 80)
    def objective_func(v_v_array):
        sim_results = _run_simulation(inputs, v_v_array[0], config)
        return (sim_results['sr'] - target_sr) ** 2

    result = minimize(objective_func, [20.0], bounds=[(1, 50)], method='L-BFGS-B', tol=1e-9)
    return result.x[0] if result.success else float('nan')

def run_simulation_from_js(data_json):
    try:
        data = json.loads(data_json)
        inputs = {k: float(v) for k, v in data.get('inputs').items()}
        config = SCENARIO_CONFIG.get(data['scenario'])
        if not config: return {'error': f"Scenario {data['scenario']} not implemented"}

        if data['option'] == '1':
            optimal_v_v = solver_for_v_v(inputs, config)
            if np.isnan(optimal_v_v): return {'error': 'Solver failed to converge. Check input parameters.'}
            final_results = _run_simulation(inputs, optimal_v_v, config)
        else: # Option 2
            final_results = _run_simulation(inputs, inputs.get('v_v', 0), config)

        if 'error' in final_results:
             return {'error': final_results['error']}

        return {
            'results': [
                {'label': 'درصد حجمی (v/v%)', 'value': f"{final_results['v_v']:.2f}", 'unit': '%'},
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
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': f'An unexpected error occurred: {str(e)}'}
