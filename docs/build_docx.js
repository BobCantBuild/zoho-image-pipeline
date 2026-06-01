// Build a Word document explaining the Customer Review Analysis dashboard.
// Non-technical user introduction, with screenshots of each section.

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun,
  Table, TableRow, TableCell, AlignmentType, HeadingLevel,
  BorderStyle, WidthType, ShadingType, LevelFormat, PageBreak,
  PageOrientation,
} = require("docx");

const SHOTS = path.join(__dirname, "screenshots");
const OUT   = path.join(__dirname, "Customer_Review_Analysis_User_Guide.docx");

// -----------------------------------------------------------------------------
const NAVY    = "1E3A8A";
const INK     = "0F172A";
const MUTED   = "475569";
const ACCENT  = "6366F1";
const GREEN   = "15803D";
const RED     = "B91C1C";
const BG_LITE = "F8FAFC";
const BORDER  = "E2E8F0";

const border = { style: BorderStyle.SINGLE, size: 4, color: BORDER };
const borders = { top: border, bottom: border, left: border, right: border };

const PAGE_W = 12240;
const MARGIN = 1080;          // 0.75"
const CONTENT_W = PAGE_W - 2 * MARGIN;   // 10080 DXA

// -----------------------------------------------------------------------------
function img(fname, widthInches) {
  const file = path.join(SHOTS, fname);
  if (!fs.existsSync(file)) throw new Error("Missing " + fname);
  const wPx = Math.round(widthInches * 96);
  // Read dimensions to preserve aspect ratio
  const { Image } = require("docx");      // not used; placeholder
  // Use width-only sizing — we know table=1600x440 etc, but stored at 2x = 3200x880
  // Get aspect ratio from PNG header
  const buf = fs.readFileSync(file);
  // PNG width/height at bytes 16-23 (big-endian uint32)
  const pngW = buf.readUInt32BE(16);
  const pngH = buf.readUInt32BE(20);
  const hPx = Math.round(wPx * pngH / pngW);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 120 },
    children: [new ImageRun({
      type: "png",
      data: buf,
      transformation: { width: wPx, height: hPx },
      altText: { title: fname, description: fname, name: fname },
    })],
  });
}

function H1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 180 },
    children: [new TextRun({ text, bold: true, size: 36, color: NAVY })],
  });
}

function H2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 140 },
    children: [new TextRun({ text, bold: true, size: 28, color: ACCENT })],
  });
}

function H3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 220, after: 100 },
    children: [new TextRun({ text, bold: true, size: 22, color: INK })],
  });
}

function P(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120, line: 300 },
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
    children: [new TextRun({
      text,
      size: 22,
      color: opts.muted ? MUTED : INK,
      italics: !!opts.italic,
      bold: !!opts.bold,
    })],
  });
}

function Bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 80, line: 280 },
    children: [new TextRun({ text, size: 22, color: INK })],
  });
}

function Caption(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 240 },
    children: [new TextRun({ text, size: 18, italics: true, color: MUTED })],
  });
}

// Simple key/value table for column descriptions
function kvTable(rows) {
  const colW = [3200, CONTENT_W - 3200];  // sums to CONTENT_W
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: colW,
    rows: rows.map(([k, v], idx) => new TableRow({
      children: [
        new TableCell({
          borders,
          width: { size: colW[0], type: WidthType.DXA },
          shading: { fill: BG_LITE, type: ShadingType.CLEAR },
          margins: { top: 100, bottom: 100, left: 140, right: 140 },
          children: [new Paragraph({ children: [
            new TextRun({ text: k, bold: true, size: 21, color: NAVY })
          ]})],
        }),
        new TableCell({
          borders,
          width: { size: colW[1], type: WidthType.DXA },
          margins: { top: 100, bottom: 100, left: 140, right: 140 },
          children: [new Paragraph({ children: [
            new TextRun({ text: v, size: 21, color: INK })
          ]})],
        }),
      ],
    })),
  });
}

// Colored info box (light background)
function infoBox(title, bodyLines, fill = "EEF2FF") {
  const cells = [
    new TableCell({
      borders,
      width: { size: CONTENT_W, type: WidthType.DXA },
      shading: { fill, type: ShadingType.CLEAR },
      margins: { top: 200, bottom: 200, left: 240, right: 240 },
      children: [
        new Paragraph({
          spacing: { after: 80 },
          children: [new TextRun({ text: title, bold: true, size: 24, color: NAVY })],
        }),
        ...bodyLines.map(line => new Paragraph({
          spacing: { after: 60, line: 280 },
          children: [new TextRun({ text: line, size: 21, color: INK })],
        })),
      ],
    }),
  ];
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [new TableRow({ children: cells })],
  });
}

// =============================================================================
//  DOCUMENT BODY
// =============================================================================

const body = [];

// COVER
body.push(
  new Paragraph({
    spacing: { before: 1600, after: 240 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "Customer Review Analysis",
      bold: true, size: 60, color: NAVY,
    })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 480 },
    children: [new TextRun({
      text: "Dashboard User Guide",
      size: 36, color: MUTED,
    })],
  }),
  img("header.png", 6.5),
  Caption("The Customer Review Analysis dashboard"),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 1200, after: 60 },
    children: [new TextRun({ text: "A simple walkthrough", size: 26, color: INK })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 60 },
    children: [new TextRun({
      text: "of every section of the dashboard",
      size: 22, color: MUTED,
    })],
  }),
  new Paragraph({ children: [new PageBreak()] }),
);

// 1 — INTRODUCTION
body.push(H1("1.  Objective"));
body.push(P("This dashboard helps the team check every customer review that comes in through our Zoho feedback form. For each review the customer uploads two screenshots — one of the order details and one of the rating screen — and the dashboard compares what was uploaded against what was filled in the form."));
body.push(P("In short, this dashboard answers three simple questions for every record:"));
body.push(Bullet("Does the Order ID the customer typed match the Order ID shown in the screenshot?"));
body.push(Bullet("What star rating did the customer actually give in the screenshot?"));
body.push(Bullet("Is the review verified — meaning everything lines up correctly?"));

body.push(H1("2.  The Problem We Are Solving"));
body.push(P("Reviews come in faster than anyone can manually inspect. Each one needs at least two checks — Order ID match and star rating — and there is no way to keep up with hundreds of records by eye."));
body.push(P("Before this dashboard:"));
body.push(Bullet("Every screenshot had to be opened one by one."));
body.push(Bullet("The Order ID had to be read off the image and compared to the form entry."));
body.push(Bullet("The star count had to be counted by hand."));
body.push(Bullet("Mistakes were easy to make and impossible to audit later."));
body.push(P("This dashboard does all of that automatically and shows the results in a single screen."));

body.push(new Paragraph({ children: [new PageBreak()] }));

// 3 — DASHBOARD AT A GLANCE
body.push(H1("3.  The Dashboard at a Glance"));
body.push(P("When you open the dashboard, you see one page with three main areas, top to bottom:"));
body.push(Bullet("Section 1 — Summary cards across the top (the headline numbers)."));
body.push(Bullet("Section 2 — Filters & search (the toolbar for narrowing down records)."));
body.push(Bullet("Section 3 — Records table (one row per customer review)."));
body.push(img("01_full_dashboard.png", 6.5));
body.push(Caption("Full dashboard — Sections 1, 2, and 3 from top to bottom"));

body.push(new Paragraph({ children: [new PageBreak()] }));

// HEADER
body.push(H1("4.  The Header"));
body.push(P("The blue banner at the very top simply tells you which dashboard you are looking at. It does not contain any data — it is purely a title bar."));
body.push(img("header.png", 6.5));
body.push(Caption("The header banner"));

// =============================================================================
// SECTION 1 — METRIC CARDS
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("5.  Section 1 — Summary Cards"));
body.push(P("Five cards across the top give you the headline picture before you look at any individual record. The numbers always reflect the whole dataset — filters down below do not change them."));
body.push(img("metrics.png", 6.5));
body.push(Caption("Section 1 — five summary cards"));

body.push(H2("5.1  In Pipeline"));
body.push(P("This is the total number of customer reviews the system has picked up — the full size of your dataset."));
body.push(infoBox(
  "Example",
  ["If the card shows 30, that means 30 customer reviews are currently loaded in the dashboard."],
));

body.push(H2("5.2  Pending"));
body.push(P("Of all the records loaded, how many have not yet been read by the system. While the pipeline is still processing screenshots, this number counts down toward zero."));
body.push(infoBox(
  "What to expect",
  ["0 means everything is processed and ready to review.",
   "A non-zero number means the system is still working — the dashboard will refresh automatically."],
));

body.push(H2("5.3  Order ID Match"));
body.push(P("Three small boxes inside one card show how the Order ID comparison turned out across all records:"));
body.push(kvTable([
  ["✓ Match",     "The Order ID in the customer's screenshot matches the Order ID they typed in the form."],
  ["✕ Mismatch",  "The two Order IDs are different (likely the customer typed it wrong, or the screenshot belongs to a different order)."],
  ["— Un-Verified", "Either the screenshot was unclear or the Order ID couldn't be read — needs a human eye."],
]));

body.push(H2("5.4  Star Rating"));
body.push(P("Three small boxes show how the star ratings break down:"));
body.push(kvTable([
  ["★ ≥ 4", "Customer gave 4 or 5 stars (a positive review)."],
  ["★ < 4", "Customer gave 3 stars or less (a negative review)."],
  ["— Un-Verified", "The system could not read the star count from the screenshot."],
]));

body.push(H2("5.5  Verified"));
body.push(P("This is the final verdict for each record:"));
body.push(kvTable([
  ["✓ YES",        "Order ID matched AND the customer gave 4+ stars — fully verified, positive review."],
  ["✕ NO",         "Either the Order ID didn't match, or the customer gave a low rating — review failed."],
  ["— Un-Verified", "Not enough information to decide — a human needs to look at this one."],
]));

// =============================================================================
// SECTION 2 — FILTERS
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("6.  Section 2 — Filters & Search"));
body.push(P("Section 2 is the toolbar you use to narrow down the records you want to see. The summary cards above always stay the same, but the table below changes as soon as you pick a filter."));
body.push(img("filters.png", 6.5));
body.push(Caption("Section 2 — search box + filter row"));

body.push(H2("6.1  Search Box"));
body.push(P("Type into the search box at the top of this section to find records by File Name, Zoho Order ID, File Order ID, or Ticket ID. The table updates as you type — no need to press Enter."));

body.push(H2("6.2  Verified"));
body.push(P("Drop-down with four options: All, YES, NO, Un-Verified. Use this to focus on (for example) only the records that failed verification."));

body.push(H2("6.3  Order ID Match"));
body.push(P("Same four options. Show only records where the Order ID matched, didn't match, or couldn't be checked."));

body.push(H2("6.4  Star Rating ≥ 4"));
body.push(P("Filter to only positive reviews (YES), only negative reviews (NO), or only the ones that couldn't be read."));

body.push(H2("6.5  Branch"));
body.push(P("Pick a single IFB branch (e.g. Jamshedpur, Karnal) to see only the reviews tagged to that branch."));

body.push(H2("6.6  Date of Posting"));
body.push(P("Choose a date range to see only the reviews submitted between those two dates. Format is day/month/year."));

body.push(H2("6.7  Export to CSV"));
body.push(P("After you have filtered down to the records you care about, this button downloads them as a CSV file you can open in Excel or share with the team."));

body.push(H2("6.8  Clear"));
body.push(P("Resets every filter, the search box, and the page number back to their defaults — useful to start fresh."));

// =============================================================================
// SECTION 3 — TABLE
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("7.  Section 3 — Records Table"));
body.push(P("Below the filters sits the main records table, with one row for every customer review. The small line just above the table tells you how many records match your current filters (\"30 records found\"). Each column tells you something different."));
body.push(img("table.png", 6.5));
body.push(Caption("Section 3 — the records table"));

body.push(H2("7.1  Column-by-Column"));
body.push(kvTable([
  ["#",                "Row number, just for reference."],
  ["Date of Posting",  "When the customer submitted the review through the form."],
  ["Branch",           "Which IFB service branch the review is tagged to."],
  ["Ticket ID",        "The unique ID assigned to this review by Zoho."],
  ["Zoho Order ID",    "The Order ID the customer typed into the form."],
  ["File Order ID",    "The Order ID the system read from the screenshot. If it differs from the Zoho Order ID, the differing characters appear in red."],
  ["Order ID Match",   "✓ YES if the two IDs match (small typos forgiven); ✕ NO if they are clearly different; — Un-Verified if one of them couldn't be read."],
  ["Service Rating",   "Stars shown when the screenshot is from the \"Installation and Demo\" page (service feedback)."],
  ["Product Rating",   "Stars shown when the screenshot is from the \"Rate your experience\" page (product feedback)."],
  ["Star Rating",      "Stars shown when the screenshot does not say Service or Product — the general rating."],
  ["Star ≥ 4",         "✓ YES if the customer gave 4 or 5 stars; ✕ NO if it was 3 or below; — Un-Verified if no stars were detected."],
  ["File Name",        "The folder name where the original screenshots are stored on disk."],
  ["✦ Verified",       "The overall verdict for this record — same three values as the summary card."],
]));

body.push(H2("7.2  Highlighting Differences"));
body.push(P("If a few digits in the File Order ID look different from the Zoho Order ID, just those characters appear in red so you can spot the mismatch at a glance. Small differences (1–3 characters) are forgiven — the Order ID Match column will still show ✓ YES because they are almost certainly the same order with a small typo."));

body.push(H2("7.3  Pagination"));
body.push(P("If your filtered list has more than 50 records, the table shows the first 50 and gives you Prev / Next buttons below the table to scroll through the rest."));

// CLOSING
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("8.  Putting It All Together"));
body.push(P("A typical session with the dashboard looks like this:"));
body.push(Bullet("Open the dashboard — look at the summary cards (Section 1) for the headline picture."));
body.push(Bullet("Use the filters (Section 2) to focus on what matters today — for example, only failed verifications from a single branch this week."));
body.push(Bullet("Read the matching records in the table (Section 3) — the red highlights tell you exactly where the Order ID differs, and the star columns tell you what the customer thought."));
body.push(Bullet("Export the filtered list to CSV when you need to hand it off to someone else."));
body.push(Bullet("Click Clear to start over with a clean view."));

body.push(P(""));
body.push(P("And that's the whole dashboard — five summary cards on top, a filter toolbar in the middle, and a detailed table at the bottom.", { italic: true, muted: true }));

// =============================================================================
const doc = new Document({
  creator: "Customer Review Analysis",
  title: "Customer Review Analysis — User Guide",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size:   { width: 12240, height: 15840 },
        margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
      },
    },
    children: body,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("Wrote", OUT);
});
