"""The single source of the application's visual design tokens.

Presentation only.  This module holds the product's display name, the approved
colour, type, spacing and shape tokens, and the one centralised stylesheet that
is injected once from the entrypoint.  It knows nothing about assessments,
policies or decisions, and nothing here may change what the product says.

The design system is deliberately narrow: one accent, square corners, hairline
borders, no shadows and no gradients.  Anything that Streamlit's own theme
configuration can express lives in ``.streamlit/config.toml`` instead of here -
this stylesheet only carries what configuration and shared Python helpers
cannot.
"""

from __future__ import annotations

import streamlit as st


# --- Product identity (presentation/branding surfaces only) -----------------
# Internal package, module, schema, token and artefact names are unaffected.
PRODUCT_NAME = "AI Adoption Assessment Tool"
PRODUCT_BYLINE = "Conceptualised and shipped by Antony Vishal."

# --- Approved palette -------------------------------------------------------
COLOR_PRIMARY = "#1F5A54"
COLOR_PRIMARY_PRESSED = "#163F3A"
COLOR_BG = "#F7F8F6"
COLOR_SURFACE = "#FFFFFF"
COLOR_SECONDARY_BG = "#EDF1EE"
COLOR_TEXT = "#17211F"
COLOR_MUTED = "#46514E"
COLOR_FAINT = "#8A9490"
COLOR_HAIRLINE = "#DCE4DF"
COLOR_INFO_BG = "#E8EEF3"
COLOR_INFO_BORDER = "#C7D6E1"
COLOR_INFO_TEXT = "#2C4A63"
COLOR_WARN_BG = "#FBF6E3"
COLOR_WARN_BORDER = "#E3D68E"
COLOR_WARN_TEXT = "#6B5A17"

# --- Type and measure -------------------------------------------------------
HEADING_FONT_STACK = '"Barlow Condensed", "Barlow", "Helvetica Neue", Arial, sans-serif'
BODY_FONT_STACK = '"Barlow", "Helvetica Neue", Arial, sans-serif'
MONO_FONT_STACK = '"SFMono-Regular", "Menlo", "Consolas", monospace'
PROSE_MEASURE_PX = 720
CONTENT_MAX_WIDTH_PX = 1180
SIDEBAR_WIDTH_PX = 248

_GLOBAL_STYLESHEET = """
:root {
  --aae-primary: #1F5A54;
  --aae-primary-pressed: #163F3A;
  --aae-bg: #F7F8F6;
  --aae-surface: #FFFFFF;
  --aae-secondary-bg: #EDF1EE;
  --aae-text: #17211F;
  --aae-muted: #46514E;
  --aae-faint: #8A9490;
  --aae-hairline: #DCE4DF;
  --aae-info-bg: #E8EEF3;
  --aae-info-border: #C7D6E1;
  --aae-info-text: #2C4A63;
  --aae-warn-bg: #FBF6E3;
  --aae-warn-border: #E3D68E;
  --aae-warn-text: #6B5A17;
  --aae-space-1: 4px;
  --aae-space-2: 8px;
  --aae-space-3: 12px;
  --aae-space-4: 16px;
  --aae-space-5: 20px;
  --aae-space-6: 24px;
  --aae-space-7: 32px;
  --aae-space-8: 48px;
  --aae-heading-font: "Barlow Condensed", "Barlow", "Helvetica Neue", Arial, sans-serif;
  --aae-body-font: "Barlow", "Helvetica Neue", Arial, sans-serif;
  --aae-mono-font: "SFMono-Regular", "Menlo", "Consolas", monospace;
  --aae-measure: 720px;
  --aae-sidebar-width: 248px;
}

/* ---------- 1. Global shape and chrome ---------------------------------- */
[data-testid="stApp"] * { box-shadow: none !important; }
[data-testid="stHeaderActionElements"] { display: none !important; }
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3 { letter-spacing: -0.01em; }

/* ---------- 2. Content width, measure and rhythm ------------------------ */
[data-testid="stMainBlockContainer"] {
  max-width: 1180px;
  padding: 32px 56px 64px;
}
[data-testid="stMain"] [data-testid="stMarkdown"] p,
[data-testid="stMain"] [data-testid="stMarkdown"] li,
[data-testid="stMain"] [data-testid="stCaptionContainer"] p {
  max-width: var(--aae-measure);
  line-height: 1.6;
}
[data-testid="stMain"] [data-testid="stMarkdown"] p { margin-bottom: 0.5rem; }
[data-testid="stMain"] h1 { margin-bottom: 2px; padding-top: 0; }
[data-testid="stMain"] h2 { margin-top: 20px; }
[data-testid="stCaptionContainer"] { color: var(--aae-muted); }
[data-testid="stMetricValue"],
[data-testid="stMetric"] { font-variant-numeric: tabular-nums; }
[data-testid="stMetric"] {
  background: var(--aae-surface);
  border: 1px solid var(--aae-hairline);
  padding: 14px 16px;
}
[data-testid="stMetricLabel"] p {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--aae-muted);
}
[data-testid="stMetricValue"] { font-family: var(--aae-heading-font); }
.aae-num { font-variant-numeric: tabular-nums; }

/* ---------- 3. Sidebar shell -------------------------------------------- */
[data-testid="stSidebar"] {
  background: var(--aae-surface);
  border-right: 1px solid var(--aae-hairline);
}
[data-testid="stSidebarUserContent"] { padding: 4px 0 24px; }
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: 0.35rem; }
[data-testid="stSidebarHeader"] { padding-bottom: 0; }

.aae-brand {
  font-family: var(--aae-heading-font);
  font-size: 19px;
  font-weight: 700;
  line-height: 1.15;
  color: var(--aae-text);
  margin: 8px 0 2px;
}
.aae-byline {
  font-size: 10.5px;
  line-height: 1.4;
  color: var(--aae-muted);
  margin: 0 0 10px;
}
.aae-rule { border-top: 1px solid var(--aae-hairline); margin: 8px 0 10px; }

/* Navigation: real page links to the registered pages, grouped and styled. */
[data-testid="stSidebar"] [data-testid="stPageLink"] a,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
  border-radius: 0;
  padding: 7px 10px;
  margin: 0;
  width: 100%;
  color: var(--aae-muted);
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a p,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {
  font-family: var(--aae-body-font);
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.3;
  overflow-wrap: break-word;
  word-break: normal;
  hyphens: none;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] > span,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  max-width: none;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
  align-items: flex-start;
  gap: 8px;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
  background: var(--aae-secondary-bg);
}
[data-testid="stSidebarUserContent"] [data-testid="stElementContainer"] { margin-bottom: 0; }
[data-testid="stSidebar"] [data-testid="stPageLink"] { margin: 0; }
.aae-eyebrow {
  display: block;
  font-family: var(--aae-body-font);
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--aae-faint);
  margin: 0 0 4px;
}

/* Assessment context block */
.aae-context-title {
  font-family: var(--aae-heading-font);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--aae-text);
  margin: 0 0 2px;
  overflow-wrap: break-word;
}
.aae-context-id {
  font-family: var(--aae-mono-font);
  font-size: 10px;
  color: var(--aae-faint);
  word-break: break-all;
  margin: 0 0 8px;
}
.aae-context-empty { font-size: 12px; color: var(--aae-faint); margin: 8px 0; }

/* Vertical stage rail: state is carried by symbol, weight and structure. */
.aae-stage { margin: 10px 0 0; border-top: 1px solid var(--aae-hairline); padding-top: 8px; }
.aae-stage-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 2px 0;
  font-size: 11.5px;
  line-height: 1.35;
  overflow-wrap: break-word;
  word-break: normal;
  hyphens: none;
}
.aae-stage-mark {
  flex: 0 0 12px;
  text-align: center;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.aae-stage-done .aae-stage-label { color: var(--aae-muted); font-weight: 400; }
.aae-stage-done .aae-stage-mark { color: var(--aae-primary); }
.aae-stage-current .aae-stage-label { color: var(--aae-text); font-weight: 600; }
.aae-stage-current .aae-stage-mark { color: var(--aae-primary); font-weight: 600; }
.aae-stage-todo .aae-stage-label { color: var(--aae-faint); font-weight: 400; }
.aae-stage-todo .aae-stage-mark { color: var(--aae-faint); }

/* ---------- 4. Alerts: disclosure banners and guard panels -------------- */
[data-testid="stAlertContainer"] {
  border-radius: 0;
  border: 1px solid var(--aae-hairline);
  padding: 12px 14px;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
  border-color: var(--aae-info-border);
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
  border-color: var(--aae-warn-border);
}
[data-testid="stAlertContainer"] p { line-height: 1.55; }

.st-key-aae-guard-panel { margin-top: 4px; max-width: var(--aae-measure); }
.st-key-aae-guard-panel [data-testid="stAlertContainer"] { padding: 18px 20px; }

/* ---------- 5. Technical disclosure ------------------------------------- */
[data-testid="stExpander"] details {
  border: 1px solid var(--aae-hairline);
  border-radius: 0;
  background: var(--aae-surface);
}
[data-testid="stExpander"] summary {
  font-family: var(--aae-body-font);
  font-size: 13px;
  font-weight: 500;
  color: var(--aae-muted);
  padding: 8px 12px;
}
[data-testid="stExpander"] summary:hover { color: var(--aae-primary); }
[data-testid="stExpanderDetails"] { padding-top: 4px; }

/* ---------- 6. Button hierarchy ----------------------------------------- */
[data-testid="stBaseButton-primary"] {
  background: var(--aae-primary);
  border: 1px solid var(--aae-primary);
  color: #FFFFFF;
  font-weight: 600;
}
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primary"]:focus,
[data-testid="stBaseButton-primary"]:active {
  background: var(--aae-primary-pressed);
  border-color: var(--aae-primary-pressed);
  color: #FFFFFF;
}
[data-testid="stMain"] [data-testid="stBaseButton-secondary"],
[data-testid="stMain"] [data-testid="stBaseButton-secondaryFormSubmit"] {
  border: 1px solid var(--aae-primary);
  color: var(--aae-primary);
  background: transparent;
  font-weight: 600;
}
[data-testid="stMain"] [data-testid="stBaseButton-secondary"]:hover,
[data-testid="stMain"] [data-testid="stBaseButton-secondaryFormSubmit"]:hover {
  background: var(--aae-secondary-bg);
  color: var(--aae-primary-pressed);
  border-color: var(--aae-primary-pressed);
}
[class*="st-key-aae-destructive-"] [data-testid="stBaseButton-secondary"],
[class*="st-key-aae-destructive-"] [data-testid="stBaseButton-secondaryFormSubmit"] {
  border: 1px solid var(--aae-hairline) !important;
  color: var(--aae-muted) !important;
  background: transparent !important;
  font-weight: 500 !important;
}
[class*="st-key-aae-destructive-"] [data-testid="stBaseButton-secondary"]:hover {
  border-color: var(--aae-muted) !important;
  background: var(--aae-secondary-bg) !important;
}

/* ---------- 7. Shared presentation primitives --------------------------- */
.aae-page-eyebrow {
  display: block;
  font-family: var(--aae-body-font);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--aae-muted);
  margin: 0 0 6px;
}
.aae-purpose {
  max-width: var(--aae-measure);
  font-size: 14px;
  line-height: 1.6;
  color: var(--aae-muted);
  margin: 8px 0 20px;
}
.aae-badge {
  display: inline-block;
  border: 1px solid var(--aae-primary);
  color: var(--aae-primary);
  border-radius: 0;
  font-family: var(--aae-body-font);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.3;
  padding: 3px 9px;
  margin: 0 4px 4px 0;
  white-space: nowrap;
}
.aae-badge--muted { border-color: var(--aae-muted); color: var(--aae-muted); }
.aae-list { max-width: var(--aae-measure); margin: 4px 0 8px; padding-left: 18px; }
.aae-list li { margin: 0 0 5px; line-height: 1.55; }
.aae-list-card {
  border: 1px solid var(--aae-hairline);
  background: var(--aae-surface);
  padding: 14px 16px;
  margin: 8px 0 12px;
  max-width: var(--aae-measure);
}
.aae-evidence {
  border: 1px solid var(--aae-hairline);
  background: var(--aae-secondary-bg);
  padding: 11px 12px;
  margin: 6px 0 4px;
  font-family: var(--aae-mono-font);
  font-size: 12px;
  line-height: 1.5;
  color: var(--aae-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.aae-locator {
  font-size: 10.5px;
  color: var(--aae-faint);
  margin: 0 0 10px;
  word-break: break-all;
}

/* ---------- 8. Responsive foundation ------------------------------------ */
@media (min-width: 641px) {
  [data-testid="stSidebar"] {
    width: var(--aae-sidebar-width) !important;
    min-width: var(--aae-sidebar-width) !important;
    max-width: var(--aae-sidebar-width) !important;
  }
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: 60px 16px 48px; max-width: 100%; }
  [data-testid="stMain"] h1 { font-size: 1.5rem; }
  [data-testid="stMain"] h2 { font-size: 1.2rem; }
  [data-testid="stMain"] [data-testid="stMarkdown"] p,
  [data-testid="stMain"] [data-testid="stMarkdown"] li { max-width: 100%; }
  .aae-purpose, .aae-list, .aae-list-card { max-width: 100%; }
  [data-testid="stVerticalBlock"] { gap: 0.6rem; }
}
"""


def global_stylesheet() -> str:
    """Return the one centralised stylesheet, without its ``<style>`` wrapper."""

    return _GLOBAL_STYLESHEET


def inject_global_styles() -> None:
    """Inject the centralised stylesheet once per rerun, from the entrypoint.

    Static design tokens only.  No document, assessment or user content is
    interpolated into this block.
    """

    st.markdown(f"<style>{_GLOBAL_STYLESHEET}</style>", unsafe_allow_html=True)
