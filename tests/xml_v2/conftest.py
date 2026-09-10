"""Exercise the POC in this checkout, without a global editable install."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "samples/tagged_pdf_xml_poc/src"))
