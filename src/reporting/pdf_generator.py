"""
PDF Report Generator -- real forensic reports rendered offline.

This module is the legacy public entry point for PDF report generation.
It delegates to `src.reporting.forensic_report`, which collects the real
backend data (adversarial scan runs, activation measurements, statistical
findings, model metadata) and renders the 18-section forensic report as a
PDF via PyQt5's QPrinter + QTextDocument. If the PDF backend is
unavailable it falls back to writing HTML and keeps the metadata row
consistent with the file actually written to disk.

No internet access is required. Output is written to the reports
directory (overridable via NEUROFENCE_REPORTS_DIR).
"""


def generate_pdf_report(output_path: str = None, scan_id=None) -> str:
    """
    Render the real forensic report as a PDF using PyQt5's QPrinter.

    Args:
        output_path: optional explicit output path; auto-generated if None.
        scan_id: optional pipeline scan id to report on (None = latest).
    Returns:
        The path to the generated file (PDF or HTML fallback).
    """
    from src.reporting.forensic_report import generate_forensic_report
    return generate_forensic_report(scan_id=scan_id, output_path=output_path)


if __name__ == "__main__":
    path = generate_pdf_report()
    print(f"Report written to: {path}")