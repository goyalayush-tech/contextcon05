import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flightback import documents
from flightback.documents import DocumentError, parse_tsv, read_document, sniff, suggest_from_document

PAGE1 = ["IndiGo flight 6E 000 Delhi to Jaipur", "Scheduled departure: 20 Nov 2026 17:00",
         "Your flight has been cancelled due to operational reasons.", "Message sent on 20/11/2026 14:05"]
PAGE2 = ["Fare break-up for booking SAMPLE1", "Basic fare Rs 3,200", "Fuel charge Rs 450", "Total Rs 5,000"]


def make_pdf(pages: list) -> bytes:
    """A real, minimal PDF with one text line per entry; an empty list makes a blank (scan-like) page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        esc = [l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for l in lines]
        stream = "BT /F1 12 Tf 16 TL 60 760 Td " + " ".join(f"({l}) Tj T*" for l in esc) + " ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def tsv(words, conf=95.0):
    head = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [f"5\t1\t1\t1\t{li}\t{wi}\t0\t0\t1\t1\t{conf}\t{w}"
            for li, line in enumerate(words, start=1) for wi, w in enumerate(line.split(), start=1)]
    return "\n".join([head, "1\t1\t0\t0\t0\t0\t0\t0\t1\t1\t-1\t"] + rows)


class FakeTools:
    """Stands in for pdftoppm and tesseract: records calls and returns canned OCR output."""

    def __init__(self, lines, conf=95.0):
        self.lines, self.conf, self.calls = lines, conf, []

    def __call__(self, cmd, **kw):
        self.calls.append(Path(cmd[0]).name)
        if cmd[0].endswith("pdftoppm"):
            Path(cmd[-1] + ".png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return subprocess.CompletedProcess(cmd, 0, tsv(self.lines, self.conf), "")


def with_tools(present=True):
    return mock.patch.object(documents.shutil, "which", lambda name: f"/usr/bin/{name}" if present else None)


class DocumentReadTests(unittest.TestCase):
    def test_file_type_comes_from_the_bytes_not_the_name(self):
        self.assertEqual(sniff(make_pdf([PAGE1])), "pdf")
        self.assertEqual(sniff(b"\x89PNG\r\n\x1a\n...."), "png")
        self.assertEqual(sniff(b"\xff\xd8\xff\xe0...."), "jpeg")
        self.assertIsNone(sniff(b"GIF89a"))
        with self.assertRaises(DocumentError) as e:
            read_document("ticket.pdf", b"not really a pdf")
        self.assertEqual(e.exception.status, 415)

    def test_empty_and_oversize_files_are_refused(self):
        with self.assertRaises(DocumentError):
            read_document("x.pdf", b"")
        with self.assertRaises(DocumentError) as e:
            read_document("x.pdf", b"%PDF-" + b"0" * documents.MAX_BYTES)
        self.assertEqual(e.exception.status, 413)

    def test_corrupt_pdf_is_an_input_error_not_a_crash(self):
        with self.assertRaises(DocumentError):
            read_document("x.pdf", b"%PDF-1.4\ngarbage that is not a pdf body")

    def test_text_layer_pdf_needs_no_ocr_and_keeps_pages_apart(self):
        tools = FakeTools([])
        with with_tools():
            r = suggest_from_document("e-ticket.pdf", make_pdf([PAGE1, PAGE2]), run=tools)
        self.assertEqual(tools.calls, [])  # text layer: no OCR ran
        self.assertEqual(r["document"]["methods"], ["text_layer"])
        self.assertEqual(r["document"]["pages"], 2)
        self.assertEqual(len(r["document"]["sha256"]), 64)
        by = {(c["suggested_field"], c["value"]): c for c in r["candidates"]}
        self.assertEqual(by[("scheduled_departure", "2026-11-20T17:00")]["page"], 1)
        self.assertEqual(by[("informed_at", "2026-11-20T14:05")]["page"], 1)
        self.assertEqual(by[("basic_fare", 3200.0)]["page"], 2)
        self.assertEqual(by[("fuel_charge", 450.0)]["page"], 2)
        self.assertFalse(by[("extraordinary_claimed", False)]["low_confidence"])
        self.assertTrue(any("cancelled by the airline" in n for n in r["notes"]))

    def test_scanned_page_is_rendered_and_ocrd_with_its_confidence(self):
        tools = FakeTools(["Scheduled departure: 20 Nov 2026 17:00"], conf=91.25)
        with with_tools():
            r = suggest_from_document("scan.pdf", make_pdf([[]]), run=tools)
        self.assertEqual(tools.calls, ["pdftoppm", "tesseract"])
        self.assertEqual(r["pages"][0]["method"], "ocr")
        self.assertEqual(r["pages"][0]["confidence"], 91.2)
        c = r["candidates"][0]
        self.assertEqual((c["suggested_field"], c["value"], c["method"], c["page"]),
                         ("scheduled_departure", "2026-11-20T17:00", "ocr", 1))

    def test_low_confidence_ocr_is_flagged_on_the_page_and_each_value(self):
        with with_tools():
            r = suggest_from_document("blurry.png", b"\x89PNG\r\n\x1a\nimg",
                                      run=FakeTools(["Basic fare Rs 3,200"], conf=41.0))
        self.assertTrue(r["candidates"][0]["low_confidence"])
        self.assertTrue(any("Low OCR confidence (41%)" in n for n in r["notes"]))

    def test_without_ocr_installed_scans_say_so_and_text_pdfs_still_work(self):
        with with_tools(present=False):
            self.assertFalse(documents.capabilities()["ocr"])
            r = suggest_from_document("scan.pdf", make_pdf([[], PAGE2]))
            self.assertEqual([p["method"] for p in r["pages"]], ["unread", "text_layer"])
            self.assertTrue(any("OCR is not installed" in n for n in r["notes"]))
            self.assertEqual({c["page"] for c in r["candidates"]}, {2})
            with self.assertRaises(DocumentError) as e:
                read_document("photo.jpg", b"\xff\xd8\xff\xe0img")
            self.assertEqual(e.exception.status, 503)

    def test_password_protected_pdf_asks_for_the_password_to_be_removed(self):
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        w.add_page(PdfReader(io.BytesIO(make_pdf([PAGE1]))).pages[0])
        w.encrypt("secret")
        buf = io.BytesIO()
        w.write(buf)
        with self.assertRaisesRegex(DocumentError, "password-protected"):
            read_document("locked.pdf", buf.getvalue())

    def test_only_the_first_pages_are_read_from_a_long_pdf(self):
        with with_tools(), mock.patch.object(documents, "MAX_PAGES", 2):
            r = read_document("long.pdf", make_pdf([PAGE1, PAGE2, PAGE1]))
        self.assertEqual(len(r["pages"]), 2)
        self.assertTrue(any("first 2 of 3 pages" in n for n in r["notes"]))

    def test_tsv_parsing_keeps_lines_and_ignores_non_words(self):
        text, conf = parse_tsv(tsv(["Basic fare Rs 3,200", "Fuel charge Rs 450"], conf=80))
        self.assertEqual(text, "Basic fare Rs 3,200\nFuel charge Rs 450")
        self.assertEqual(conf, 80.0)
        self.assertEqual(parse_tsv("header only"), ("", None))


class EvidenceIndexTests(unittest.TestCase):
    def test_page_method_and_document_hash_reach_the_evidence_index(self):
        from flightback.packet import build_case
        payload = {"case_type": "cancellation", "flight": {"operating_carrier": "6E"},
                   "facts": {"basic_fare": {"value": 3200, "doc": "scan.pdf", "snippet": "Basic fare Rs 3,200",
                                            "page": 2, "method": "ocr", "confidence": 91.2, "doc_sha256": "ab" * 32}}}
        e = build_case(payload)["evidence_index"][0]
        self.assertEqual((e["page"], e["method"], e["confidence"], e["doc_sha256"]), (2, "ocr", 91.2, "ab" * 32))
        self.assertEqual(e["provenance"], "document (OCR, confirmed by passenger)")


class UploadApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("FLIGHTBACK_DB", tempfile.mktemp(suffix=".db"))  # never the real flightback.db
        os.environ.setdefault("CRUSTDATA_API_KEY", "")
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            raise unittest.SkipTest("needs fastapi + httpx")
        from flightback.app import app
        cls.c = TestClient(app)

    def test_upload_a_pdf_and_get_page_tagged_suggestions(self):
        r = self.c.post("/api/documents", files={"file": ("e-ticket.pdf", make_pdf([PAGE1, PAGE2]), "application/pdf")})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["document"]["name"], "e-ticket.pdf")
        self.assertTrue(all("page" in c and "method" in c for c in body["candidates"]))
        self.assertIn(2, {c["page"] for c in body["candidates"]})

    def test_wrong_file_type_is_415_even_with_a_pdf_name(self):
        r = self.c.post("/api/documents", files={"file": ("e-ticket.pdf", b"hello", "application/pdf")})
        self.assertEqual(r.status_code, 415)
        self.assertIn("PDF, PNG or JPEG", r.json()["detail"])

    def test_capabilities_report_what_this_server_can_read(self):
        caps = self.c.get("/api/documents/capabilities").json()
        self.assertTrue(caps["text_layer"])
        self.assertEqual(caps["ocr"], bool(shutil.which("tesseract")))


@unittest.skipUnless(shutil.which("tesseract") and shutil.which("pdftoppm"), "needs tesseract and poppler installed")
class RealOcrTests(unittest.TestCase):
    """End to end with the real binaries: a rendered page image goes through tesseract and back into facts."""

    def test_real_ocr_reads_a_rendered_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "t.pdf"
            pdf.write_bytes(make_pdf([PAGE1 + PAGE2]))
            subprocess.run(["pdftoppm", "-r", "200", "-png", "-singlefile", str(pdf), str(Path(tmp) / "t")], check=True)
            png = (Path(tmp) / "t.png").read_bytes()
        r = suggest_from_document("screenshot.png", png)
        self.assertEqual(r["pages"][0]["method"], "ocr")
        self.assertGreater(r["pages"][0]["confidence"], 70)
        vals = {(c["suggested_field"], c["value"]) for c in r["candidates"]}
        self.assertIn(("scheduled_departure", "2026-11-20T17:00"), vals)
        self.assertIn(("basic_fare", 3200.0), vals)

    @unittest.skipUnless(shutil.which("sips"), "needs macOS sips to build an image-only PDF")
    def test_real_scanned_pdf_falls_back_to_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "t.pdf"
            pdf.write_bytes(make_pdf([PAGE2]))
            subprocess.run(["pdftoppm", "-r", "200", "-png", "-singlefile", str(pdf), str(Path(tmp) / "t")], check=True)
            subprocess.run(["sips", "-s", "format", "pdf", str(Path(tmp) / "t.png"), "--out", str(Path(tmp) / "scan.pdf")],
                           check=True, capture_output=True)
            scan = (Path(tmp) / "scan.pdf").read_bytes()
        r = suggest_from_document("scan.pdf", scan)
        self.assertEqual(r["pages"][0]["method"], "ocr")
        self.assertIn(("fuel_charge", 450.0), {(c["suggested_field"], c["value"]) for c in r["candidates"]})


if __name__ == "__main__":
    unittest.main()
