

import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import streamlit as st
import pandas as pd
import json
import os
import hashlib
from datetime import datetime

from security.sandbox import run_sandbox

st.set_page_config(
    page_title="NeuroFence",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- STYLE ----------
st.markdown("""
<style>
.main {
    background: #080b12;
}
.block-container {
    padding-top: 1.5rem;
}
.title {
    font-size: 42px;
    font-weight: 800;
    color: #00e5ff;
}
.subtitle {
    color: #8b95a7;
    font-size: 16px;
}
.card {
    background: #111722;
    padding: 22px;
    border-radius: 14px;
    border: 1px solid #202938;
}
.metric {
    font-size: 32px;
    font-weight: 700;
}
.small {
    color: #8994a7;
}
</style>
""", unsafe_allow_html=True)


# ---------- HELPERS ----------
def score_to_risk(score):
    if score < 2:
        return "LOW", "🟢"
    elif score < 4:
        return "MEDIUM", "🟡"
    return "HIGH", "🔴"


def model_hash():
    model_path = "baseline_data.json"

    if os.path.exists(model_path):
        with open(model_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]

    return "N/A"


# ---------- HEADER ----------
st.markdown(
    '<div class="title">🧠 NeuroFence</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Offline AI Model Forensics & Backdoor Detection Platform'
    '</div>',
    unsafe_allow_html=True
)

st.divider()


# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("🛡️ NeuroFence")

    st.success("● SYSTEM ONLINE")

    st.markdown("### Model")
    st.write("**distilgpt2**")
    st.caption("Local Transformer Model")

    st.markdown("### Security")
    st.write("Activation Analysis")
    st.write("Baseline Comparison")
    st.write("Anomaly Detection")

    st.markdown("### Model Fingerprint")
    st.code(model_hash())

    st.divider()
    st.caption("Air-gapped / Offline Security")


# ---------- PROMPT ----------
st.subheader("🔍 Security Scanner")

prompt = st.text_area(
    "Enter a prompt to scan",
    placeholder="Enter normal or suspicious input here...",
    height=120
)

scan = st.button(
    "🚀 RUN SECURITY SCAN",
    type="primary",
    use_container_width=True
)


# ---------- SCAN ----------
if scan:

    if not prompt.strip():
        st.warning("Please enter a prompt.")
        st.stop()

    with st.spinner("Running NeuroFence forensic analysis..."):

        try:
            result = run_sandbox(prompt)

            security = result["security"]
            decision = result["decision"]
            response = result["response"]

            st.session_state["result"] = result

        except Exception as e:
            st.error(f"Security scan failed: {e}")
            st.stop()


# ---------- RESULTS ----------
if "result" in st.session_state:

    result = st.session_state["result"]

    security = result["security"]
    decision = result["decision"]
    response = result["response"]

    status = security.get("status", "UNKNOWN")
    score = float(security.get("score", 0))
    action = decision.get("action", "REVIEW")
    layers = security.get("layer_scores", {})

    risk, icon = score_to_risk(score)

    st.divider()
    st.subheader("📊 Security Overview")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f'<div class="card">'
            f'<div class="small">SECURITY STATUS</div>'
            f'<div class="metric">{icon} {status}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            f'<div class="card">'
            f'<div class="small">ANOMALY SCORE</div>'
            f'<div class="metric">{score:.2f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f'<div class="card">'
            f'<div class="small">RISK LEVEL</div>'
            f'<div class="metric">{risk}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c4:
        st.markdown(
            f'<div class="card">'
            f'<div class="small">DECISION</div>'
            f'<div class="metric">{action}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.divider()

    # ---------- LAYER ANALYSIS ----------
    left, right = st.columns([1.5, 1])

    with left:

        st.subheader("🧬 Neural Activation Analysis")

        if layers:

            df = pd.DataFrame(
                list(layers.items()),
                columns=["Layer", "Anomaly Score"]
            )

            df["Layer"] = df["Layer"].astype(str)

            st.bar_chart(
                df.set_index("Layer")
            )

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

        else:
            st.info("No layer activation data available.")

    with right:

        st.subheader("🛡️ Security Decision")

        if action == "ALLOW":
            st.success(
                "✅ INPUT ALLOWED\n\n"
                "Activation pattern is within the normal baseline."
            )

        elif action == "MONITOR":
            st.warning(
                "⚠️ INPUT UNDER MONITORING\n\n"
                "Activation pattern is suspicious."
            )

        elif action == "BLOCK":
            st.error(
                "🚨 INPUT BLOCKED\n\n"
                "Anomalous activation pattern detected."
            )

        else:
            st.warning(
                "🔎 MANUAL REVIEW REQUIRED"
            )

    # ---------- RESPONSE ----------
    st.divider()

    st.subheader("🤖 Model Response")

    st.code(
        response,
        language="text"
    )

    # ---------- FORENSIC DETAILS ----------
    with st.expander("🔬 View Forensic Details"):

        st.json({
            "status": status,
            "anomaly_score": score,
            "risk_level": risk,
            "decision": action,
            "layers_analyzed": len(layers),
            "timestamp": datetime.now().isoformat()
        })

    # ---------- PROMPT ----------
    with st.expander("📝 Scanned Input"):
        st.write(prompt if "prompt" in locals() else "Previous scan")