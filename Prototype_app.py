# Prototype_app.py — interactive Streamlit front end for the ASI-PLC Monte Carlo check
#
# Companion code for:
#   Ashraf, S. R. B., Rahman, H., Noche, B., and Gürpinar, T.
#   "Adaptive Trust Chain: a permissioned blockchain framework for enforcing
#   weld-parameter compliance at the controller level in green hydrogen
#   infrastructure." Frontiers in Blockchain (under review).
#
# Uses exactly the same simulation core as Prototype.py (atc_sim.py), so the
# default settings reproduce Supplementary Table S2. Intended for exploratory
# runs; it is not a substitute for field deployment or a hardware test.
#
# Run:  streamlit run Prototype_app.py
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import streamlit as st

from atc_sim import (SEED, FaultType, PLCState, PLCCycleResult,
                     is_false_permit, run_simulation)

sns.set_style('whitegrid')


def summarize_results(results: List[PLCCycleResult]):
    valid_results = [r for r in results if r.fault_type == FaultType.NONE]
    noncomply_results = [r for r in results if r.fault_type == FaultType.NON_COMPLY]
    mitm_results = [r for r in results if r.fault_type == FaultType.MITM]
    replay_results = [r for r in results if r.fault_type == FaultType.REPLAY]
    timeout_results = [r for r in results if r.fault_type == FaultType.TIMEOUT]

    valid_latencies = np.array([r.latency_ms for r in valid_results])

    # False permit: Compliance Bit TRUE on a non-compliant, unverified, replayed
    # or late (> 500 ms) payload (manuscript Section 3.4.3)
    total_false_permits = sum(1 for r in results if is_false_permit(r))
    total_false_negatives = sum(1 for r in valid_results if not r.compliance_bit)

    state_counts = {
        state.value: sum(1 for r in results if r.state == state)
        for state in PLCState
    }

    return {
        'valid_results': valid_results,
        'noncomply_results': noncomply_results,
        'mitm_results': mitm_results,
        'replay_results': replay_results,
        'timeout_results': timeout_results,
        'valid_latencies': valid_latencies,
        'false_permits': total_false_permits,
        'false_negatives': total_false_negatives,
        'state_counts': state_counts,
    }


def plot_latency_histogram(latencies):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(latencies, bins=25, color='#2E7D32', edgecolor='white', alpha=0.8)
    ax.set_title('Valid Scenario Latency Distribution')
    ax.set_xlabel('Latency (ms)')
    ax.set_ylabel('Count')
    return fig


def plot_state_distribution(state_counts):
    names = list(state_counts.keys())
    values = list(state_counts.values())
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(names, values, color=['#455A64', '#2E7D32', '#C62828', '#E65100', '#4A148C'][:len(names)])
    ax.set_title('PLC State Distribution')
    ax.set_ylabel('Count')
    plt.xticks(rotation=45, ha='right')
    return fig


def app():
    st.set_page_config(page_title='ATC — ASI-PLC Monte Carlo', layout='wide')
    st.title('Adaptive Trust Chain — ASI-PLC interlock simulator')
    st.write('Interactive Monte Carlo check of the ASI-PLC production-permissive interlock (Algorithm 2). '
             'The ASI is not a safety function; latencies are drawn from assumed distributions. '
             'The defaults (seed 2025, 120/50/10/10/10 runs) reproduce Supplementary Table S2.')

    with st.sidebar:
        st.header('Simulation controls')
        seed = st.number_input('Random seed', min_value=0, value=SEED, step=1)
        n_valid = st.number_input('Valid scenarios', min_value=0, value=120, step=10)
        n_noncomply = st.number_input('Non-compliant scenarios', min_value=0, value=50, step=10)
        n_mitm = st.number_input('MitM attack scenarios', min_value=0, value=10, step=5)
        n_replay = st.number_input('Replay attack scenarios', min_value=0, value=10, step=5)
        n_timeout = st.number_input('Timeout scenarios', min_value=0, value=10, step=5)
        st.write('---')
        run_button = st.button('Run simulation')

    scenario_plan = [
        (n_valid,     FaultType.NONE,       True,  'COMPLIANT'),
        (n_noncomply, FaultType.NON_COMPLY,  False, 'PREHEAT_LOW'),
        (n_mitm,      FaultType.MITM,        True,  'COMPLIANT'),
        (n_replay,    FaultType.REPLAY,       True,  'COMPLIANT'),
        (n_timeout,   FaultType.TIMEOUT,      True,  'COMPLIANT'),
    ]

    if run_button:
        with st.spinner('Running simulation...'):
            results = run_simulation(seed, scenario_plan)
            summary = summarize_results(results)

        st.success('Simulation complete')

        col1, col2 = st.columns(2)
        col1.metric('Total scenarios', len(results))
        col1.metric('False permits (relay on non-compliant weld)', summary['false_permits'])
        col1.metric('False negatives', summary['false_negatives'])
        col2.metric('Valid results', len(summary['valid_results']))
        col2.metric('Soft lock count', len(summary['timeout_results']))
        col2.metric('Hard lock events', len([r for r in results if r.state == PLCState.HARD_LOCK]))

        st.pyplot(plot_latency_histogram(summary['valid_latencies']))
        st.pyplot(plot_state_distribution(summary['state_counts']))

        st.subheader('Scenario details')
        first_table = [
            {
                'idx': r.scenario_id,
                'fault': r.fault_type.value,
                'state': r.state.value,
                'relay_on': r.relay_on,
                'latency_ms': f'{r.latency_ms:.1f}',
                'failures': '; '.join(r.step_failures),
            }
            for r in results[:30]
        ]
        st.table(first_table)

        st.subheader('Full state counts')
        st.json(summary['state_counts'])
    else:
        st.info('Adjust the controls and click Run simulation to launch the prototype.')


if __name__ == '__main__':
    app()
