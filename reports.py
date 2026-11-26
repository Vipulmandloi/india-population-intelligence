"""Standalone, printable reports built from the displayed aggregate rows."""

from html import escape

NOTICE = "Synthetic scenario data. Figures do not represent actual people or official Indian statistics."
PROVENANCE = (
    "India Population Intelligence v3.4 validated DuckDB aggregates. The release retains selected "
    "historically calibrated dimensions and independently generated assumptions. Income includes "
    "generated zeros. Wealth labels are assigned to people. No estimate of sampling uncertainty "
    "or statistical significance is supplied."
)


def export_csv(frame, title, scope, version):
    result = frame.assign(Report=title, Scope=scope, Dataset=f"Synthetic {version}", Notice=NOTICE)
    def safe_text(value):
        if isinstance(value, str) and (value.startswith(("\t", "\r", "\n")) or
                                      value.lstrip().startswith(("=", "+", "-", "@"))):
            return "'" + value
        return value

    result = result.map(safe_text)
    result.columns = [safe_text(column) for column in result.columns]
    return result.to_csv(index=False).encode("utf-8")


def printable_report(title, scope, version, sections):
    heading = escape(title)
    body = "".join(
        f"<h2>{escape(label)}</h2>{frame.to_html(index=False, border=0, escape=True, na_rep='Unavailable', float_format=lambda value: format(value, ',.4f'))}"
        for label, frame in sections
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{heading}</title><style>
body{{max-width:1100px;margin:2rem auto;padding:0 1rem;font:15px/1.55 system-ui;color:#132437}}
h1,h2{{line-height:1.2}} table{{width:100%;border-collapse:collapse;margin:1rem 0 2rem}}
th,td{{border-bottom:1px solid #cbd5e1;padding:.4rem;text-align:left;vertical-align:top}}
th{{background:#edf4f7}} @media print{{body{{margin:0}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}
</style></head><body><h1>{heading}</h1>
<p><strong>Scope:</strong> {escape(scope)} | <strong>Dataset:</strong> Synthetic {escape(version)}</p>
<p>{escape(NOTICE)}</p><p>{escape(PROVENANCE)}</p>{body}</body></html>""".encode("utf-8")
