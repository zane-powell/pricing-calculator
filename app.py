"""
app.py — The Streamlit web interface.

This is what runs when you do:   streamlit run app.py

It collects inputs from the user, calls the pure functions in pricing.py,
and displays the result. All business logic lives in pricing.py and renewal.py;
this file is just the UI wrapper.

Streamlit basics you'll see in this file:
  st.title / st.header        — page hierarchy
  st.text_input / st.selectbox — form widgets
  st.number_input              — number entry with min/step controls
  st.file_uploader             — drag-and-drop file upload
  st.columns                   — split the page into side-by-side columns
  st.metric                    — display a big number with a label
  st.button                    — a clickable button
  st.session_state             — Streamlit's way of remembering state
                                 between reruns (the page reruns top-to-bottom
                                 every time a widget changes).

Why session_state matters here:
  Streamlit reruns the whole script on every interaction. To let the
  "Renewal mode" feature push computed values into the volume inputs,
  we have to store those values somewhere that survives reruns —
  that's what session_state is for.
"""

import streamlit as st

import data
import pdf_export
import pricing
import renewal


# ---------------------------------------------------------------------------
# Page config — sets the browser tab title, icon, and layout.
# Must be the first Streamlit command in the script.
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Thirdfort Pricing Calculator",
    page_icon="💼",
    layout="wide",
)

st.title("💼 Thirdfort Pricing Calculator")
st.caption("Generate a 3-tier pricing quote based on a client's monthly check volumes.")


# ---------------------------------------------------------------------------
# Initialize session state defaults
# ---------------------------------------------------------------------------
# These run once on first load, then session_state preserves any user changes
# (or values pushed in by the renewal flow) across page reruns.
DEFAULT_VOLUMES = {product: 0 for product in data.PRODUCTS}
DEFAULT_VOLUMES["Enhanced NFC ID"] = 290
DEFAULT_VOLUMES["KYB - Summary Report"] = 50
DEFAULT_VOLUMES["KYB - UBO"] = 50

for product in data.PRODUCTS:
    key = f"vol_{product}"
    if key not in st.session_state:
        st.session_state[key] = DEFAULT_VOLUMES[product]


# ---------------------------------------------------------------------------
# Renewal mode — import from Looker (optional, top of main area)
# ---------------------------------------------------------------------------
# An expander keeps this out of the way for new-business quotes.
# When opened, it lets the user upload Looker exports and auto-populate
# the volume inputs based on historical usage.
with st.expander(
    "📊 Renewal mode — Import volumes from Looker (optional)",
    expanded=False,
):
    st.caption(
        "Upload your Looker exports to auto-calculate monthly volumes from "
        "the client's actual usage history. Useful for renewal quotes."
    )

    upload_col1, upload_col2 = st.columns(2)
    with upload_col1:
        checks_file = st.file_uploader(
            "Completed checks export *(required)*",
            type=["xlsx", "xls", "csv"],
            key="upload_checks",
        )
    with upload_col2:
        om_file = st.file_uploader(
            "Ongoing Monitoring export *(optional)*",
            type=["xlsx", "xls", "csv"],
            key="upload_om",
        )

    # Process uploaded files
    if checks_file is not None:
        try:
            checks_df = renewal.parse_completed_checks(checks_file)
            om_series = renewal.parse_ongoing_monitoring(om_file) if om_file else None

            # Auto-detect partial months as a starting suggestion
            partial_months = renewal.detect_partial_months(checks_df)

            # Show the raw data so the user can sanity-check
            st.markdown("**Data preview** (months × Looker products)")
            st.dataframe(
                checks_df.style.format("{:.0f}"),
                use_container_width=True,
            )

            # --- Controls --------------------------------------------------
            st.markdown("**Configuration**")
            stat_col, info_col = st.columns([1, 2])
            with stat_col:
                statistic = st.radio(
                    "Aggregate using:",
                    options=["mean", "median"],
                    index=0,  # default mean — works better for OM and roughly equivalent for everything else
                    horizontal=True,
                    key="renewal_statistic",
                )
            with info_col:
                st.caption(
                    "💡 **Mean** is the default because Ongoing Monitoring "
                    "accumulates over time and median can mislead. Switch to "
                    "**median** if there are big outliers in any one month."
                )

            # --- Month selection ------------------------------------------
            st.markdown("**Months to include in the calculation**")
            if partial_months:
                partial_labels = [m.strftime("%b %Y") for m in partial_months]
                st.warning(
                    f"⚠️ Auto-flagged as likely partial: {', '.join(partial_labels)}. "
                    f"Defaulting to **exclude** these. Untick to include."
                )

            # Render a checkbox per month, in chronological order
            included_months = []
            month_cols = st.columns(min(len(checks_df.index), 4))
            for i, month in enumerate(checks_df.index):
                col = month_cols[i % len(month_cols)]
                is_partial = month in partial_months
                label = month.strftime("%b %Y")
                if is_partial:
                    label += " ⚠️"
                # Default: include unless auto-flagged as partial
                default_checked = not is_partial
                checked = col.checkbox(
                    label,
                    value=default_checked,
                    key=f"include_{month.strftime('%Y_%m')}",
                )
                if checked:
                    included_months.append(month)

            # --- Computed volumes preview ---------------------------------
            if included_months:
                computed = renewal.compute_monthly_volumes(
                    checks_df=checks_df,
                    om_series=om_series,
                    included_months=included_months,
                    statistic=statistic,
                )

                st.markdown(
                    f"**Computed monthly volumes** "
                    f"({statistic} of {len(included_months)} months)"
                )

                # Show only non-zero values; the rest defaults to 0 and
                # cluttering the screen with them isn't useful.
                shown = {k: v for k, v in computed.items() if v > 0}
                if shown:
                    preview_cols = st.columns(min(len(shown), 4))
                    for i, (product, volume) in enumerate(shown.items()):
                        preview_cols[i % len(preview_cols)].metric(
                            product, f"{volume:,}/mo"
                        )
                else:
                    st.write("_All computed volumes are zero._")

                # Apply button — pushes the computed values into session_state
                # so the sidebar inputs pick them up on the next rerun.
                if st.button(
                    "✓ Apply these values to the calculator inputs",
                    type="primary",
                    use_container_width=True,
                ):
                    for product, value in computed.items():
                        st.session_state[f"vol_{product}"] = value
                    st.success(
                        "Applied — see the sidebar. You can still tweak "
                        "individual values before generating."
                    )
                    st.rerun()
            else:
                st.error("Select at least one month to compute volumes.")

        except Exception as e:
            st.error(
                f"Couldn't parse the file. Make sure it's a Looker export in "
                f"the standard format. Error: `{e}`"
            )


# ---------------------------------------------------------------------------
# Sidebar: inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Client inputs")

    client_name = st.text_input("Client name", value="Debenhams Ottaway")
    vertical = st.selectbox("Vertical", options=data.VERTICALS, index=1)  # default Legal

    st.divider()
    st.subheader("Monthly check volumes")
    st.caption("How many of each check type the client runs per month.")

    # NOTE: these widgets use the `key` parameter only (no `value=`) so that
    # session_state drives their values. This is what lets the renewal flow
    # programmatically update them.
    monthly_volumes = {}
    for product in data.PRODUCTS:
        st.number_input(
            label=product,
            min_value=0,
            step=10,
            key=f"vol_{product}",
        )
        monthly_volumes[product] = st.session_state[f"vol_{product}"]

    # --- Free credits (optional sales sweetener) -------------------------
    st.divider()
    st.subheader("Free credits (optional)")
    st.caption(
        "Bonus credits given by sales as a sweetener. "
        "They reduce credits-to-purchase but cost £0."
    )

    tier_labels_for_inputs = data.TIER_DISPLAY_NAMES[vertical]
    free_credits_by_tier = {}
    for tier_key, tier_label in zip(data.TIER_KEYS, tier_labels_for_inputs):
        free_credits_by_tier[tier_key] = st.number_input(
            label=f"Free credits — {tier_label}",
            min_value=0,
            value=0,
            step=10,
            key=f"free_{tier_key}",
        )

    # --- Recommended tier (used in the PDF) ------------------------------
    st.divider()
    st.subheader("Recommended tier")
    st.caption("Highlighted in the tier comparison and detailed in the PDF.")
    # Map display label back to internal key for build_pdf
    recommended_tier_label = st.radio(
        "Recommended:",
        options=tier_labels_for_inputs,
        index=1,  # default to middle tier
        label_visibility="collapsed",
    )
    recommended_tier_key = data.TIER_KEYS[
        tier_labels_for_inputs.index(recommended_tier_label)
    ]

    st.divider()
    generate = st.button("Generate quote", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Main area: results
# ---------------------------------------------------------------------------
if not generate:
    st.info(
        "👈 Fill in the inputs (or use Renewal mode above) and click "
        "**Generate quote** to see the results."
    )
    st.stop()

# Build the quote — this is the only call to our pricing logic.
quote = pricing.build_quote(
    client_name=client_name,
    vertical=vertical,
    monthly_volumes=monthly_volumes,
    free_credits_by_tier=free_credits_by_tier,
)

# --- Header summary ------------------------------------------------------
st.header(f"Quote for {quote.client_name}")
col1, col2, col3 = st.columns(3)
col1.metric("Vertical", quote.vertical)
col2.metric("Monthly volume", f"{sum(quote.monthly_volumes.values()):,}")
col3.metric("Annual credits required", f"{quote.annual_credits_required:,}")

# --- Download PDF button -------------------------------------------------
# Generate the PDF on every quote generation so it's ready to download instantly.
# It's quick (sub-second) so this is fine; if it ever became slow we'd lazily
# generate on click instead.
try:
    pdf_bytes = pdf_export.build_pdf(
        quote=quote,
        recommended_tier_key=recommended_tier_key,
    )
    # Build a sensible filename
    safe_client = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_"
                          for c in quote.client_name).strip().replace(" ", "_")
    pdf_filename = f"{safe_client}_{quote.vertical.replace(' & ', '_')}_proposal.pdf"

    st.download_button(
        label="📄 Download PDF proposal",
        data=pdf_bytes,
        file_name=pdf_filename,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
except Exception as e:
    st.warning(f"Couldn't generate PDF: {e}")

st.divider()

# --- Three tiers side by side -------------------------------------------
st.subheader("Tier comparison")

tier_columns = st.columns(3)
for column, tier in zip(tier_columns, quote.tiers):
    with column:
        st.markdown(f"### {tier.tier_label}")
        st.metric("Annual total", f"£{tier.annual_total:,.0f}")
        st.metric("Monthly total", f"£{tier.monthly_total:,.0f}")
        st.metric("Cost per credit", f"£{tier.cost_per_credit:.3f}")

        with st.expander("Breakdown"):
            st.write(f"**Base platform fee:** £{tier.base_fee:,.0f}")
            st.write(f"**Credit cost:** £{tier.credit_cost:,.0f}")
            st.write(f"**Included credits:** {tier.included_credits:,}")

            if tier.free_credits > 0:
                st.write(f"**Free credits:** {tier.free_credits:,}")
                st.write(
                    f"  • Upfront: {tier.free_credits_upfront:,}  "
                    f"  • Split monthly: {tier.free_credits_monthly:,} "
                    f"(_{tier.free_credits_monthly // 12:,}/month_)"
                )

            st.write(f"**Credits to purchase:** {tier.credits_to_purchase:,}")
            st.write(
                f"**Package-adjusted credits:** {tier.package_adjusted_credits:,}  "
                f"_(rounded up to package boundaries)_"
            )
            st.write("**Credits purchased per band:**")
            for band_index, credits_in_band in enumerate(tier.purchases_by_band, start=1):
                if credits_in_band > 0:
                    band = data.BANDS[band_index - 1]
                    price = band["prices"][tier.tier_key]
                    st.write(
                        f"- Band {band_index}: {credits_in_band:,} credits "
                        f"× £{price:.2f} = £{credits_in_band * price:,.0f}"
                    )

st.divider()

# --- Inputs recap ---------------------------------------------------------
with st.expander("📋 Inputs used", expanded=False):
    st.write(f"**Client:** {quote.client_name}")
    st.write(f"**Vertical:** {quote.vertical}")
    st.write("**Monthly volumes:**")
    nonzero = {k: v for k, v in quote.monthly_volumes.items() if v > 0}
    if nonzero:
        for product, volume in nonzero.items():
            st.write(f"- {product}: {volume:,}/month")
    else:
        st.write("_No products with non-zero volume._")
