// Build a PowerPoint deck explaining the Customer Review Analysis dashboard.
// Non-technical, screenshot-driven, one section per slide.

const fs   = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const SHOTS = path.join(__dirname, "screenshots");
const OUT   = path.join(__dirname, "Customer_Review_Analysis_User_Guide.pptx");

// Palette — Midnight Executive
const NAVY    = "1E2761";
const DEEP    = "0F1E4D";
const ICE     = "CADCFC";
const WHITE   = "FFFFFF";
const INK     = "0F172A";
const MUTED   = "64748B";
const ACCENT  = "6366F1";
const SOFT_BG = "F8FAFC";
const GREEN   = "15803D";
const RED     = "B91C1C";
const AMBER   = "B45309";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";   // 13.333 x 7.5 inches
const W = 13.333;
const H = 7.5;

// -----------------------------------------------------------------------------
// SLIDE BUILDERS
// -----------------------------------------------------------------------------

function addFooter(slide, label) {
  slide.addText("Customer Review Analysis  ·  User Guide", {
    x: 0.4, y: H - 0.4, w: 6, h: 0.3,
    fontSize: 10, color: MUTED, fontFace: "Calibri",
  });
  slide.addText(label, {
    x: W - 1.5, y: H - 0.4, w: 1.1, h: 0.3,
    fontSize: 10, color: MUTED, fontFace: "Calibri",
    align: "right",
  });
}

function addSectionHeader(slide, sectionLabel, title) {
  // Section pill in upper-left
  slide.addShape(pres.ShapeType.roundRect, {
    x: 0.5, y: 0.4, w: 1.6, h: 0.36,
    fill: { color: ACCENT },
    line: { color: ACCENT, width: 0 },
    rectRadius: 0.18,
  });
  slide.addText(sectionLabel.toUpperCase(), {
    x: 0.5, y: 0.4, w: 1.6, h: 0.36,
    fontSize: 11, color: WHITE, bold: true,
    fontFace: "Calibri", align: "center", valign: "middle",
    charSpacing: 2,
  });
  // Title
  slide.addText(title, {
    x: 0.5, y: 0.9, w: W - 1.0, h: 0.7,
    fontSize: 32, bold: true, color: NAVY, fontFace: "Calibri",
  });
}

// =============================================================================
//  1 — TITLE SLIDE
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // Decorative accent strip on the left
  s.addShape(pres.ShapeType.rect, {
    x: 0, y: 0, w: 0.4, h: H,
    fill: { color: ACCENT }, line: { color: ACCENT, width: 0 },
  });

  s.addText("Customer Review", {
    x: 1.2, y: 2.1, w: 11, h: 1.1,
    fontSize: 60, bold: true, color: WHITE, fontFace: "Calibri",
  });
  s.addText("Analysis", {
    x: 1.2, y: 3.0, w: 11, h: 1.1,
    fontSize: 60, bold: true, color: ICE, fontFace: "Calibri",
  });

  // Divider
  s.addShape(pres.ShapeType.line, {
    x: 1.2, y: 4.4, w: 2.0, h: 0,
    line: { color: ACCENT, width: 3 },
  });

  s.addText("Dashboard User Guide", {
    x: 1.2, y: 4.6, w: 11, h: 0.5,
    fontSize: 22, color: ICE, fontFace: "Calibri",
  });
  s.addText("A walkthrough of every section, control, and column", {
    x: 1.2, y: 5.1, w: 11, h: 0.4,
    fontSize: 16, color: "9CB4D8", italic: true, fontFace: "Calibri",
  });

  // Magnifier icon callout
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.5, y: 5.3, w: 1.6, h: 1.6,
    fill: { color: ACCENT },
    line: { color: ICE, width: 2 },
  });
  s.addText("🔍", {
    x: 10.5, y: 5.3, w: 1.6, h: 1.6,
    fontSize: 60, color: WHITE, align: "center", valign: "middle",
  });
}

// =============================================================================
//  2 — OBJECTIVE
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Objective", "What this dashboard is for");

  // 3 numbered cards
  const items = [
    ["1", "Does the Order ID match?",      "Compare the Order ID the customer typed in the form against the Order ID visible in their screenshot."],
    ["2", "What star rating did they give?", "Read the number of stars directly from the screenshot — no manual counting."],
    ["3", "Is the review verified?",        "Combine both checks into one clear verdict: YES, NO, or Un-Verified."],
  ];
  const yStart = 2.0;
  const cardH = 1.5;
  const cardW = 12.0;
  items.forEach(([num, title, body], idx) => {
    const y = yStart + idx * (cardH + 0.25);
    // Card
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.7, y, w: cardW, h: cardH,
      fill: { color: SOFT_BG },
      line: { color: "E2E8F0", width: 1 },
      rectRadius: 0.1,
    });
    // Number badge
    s.addShape(pres.ShapeType.ellipse, {
      x: 0.95, y: y + 0.3, w: 0.9, h: 0.9,
      fill: { color: NAVY }, line: { color: NAVY, width: 0 },
    });
    s.addText(num, {
      x: 0.95, y: y + 0.3, w: 0.9, h: 0.9,
      fontSize: 28, bold: true, color: WHITE,
      fontFace: "Calibri", align: "center", valign: "middle",
    });
    // Title + body
    s.addText(title, {
      x: 2.1, y: y + 0.22, w: cardW - 1.5, h: 0.5,
      fontSize: 20, bold: true, color: INK, fontFace: "Calibri",
    });
    s.addText(body, {
      x: 2.1, y: y + 0.72, w: cardW - 1.5, h: 0.7,
      fontSize: 14, color: MUTED, fontFace: "Calibri",
    });
  });

  addFooter(s, "Slide 2");
}

// =============================================================================
//  3 — PROBLEM STATEMENT
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Problem", "Why we needed this dashboard");

  // Two columns: Before  /  Now
  const colY = 1.95;
  const colH = 4.7;

  // Before card
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: colY, w: 5.95, h: colH,
    fill: { color: "FEF2F2" }, line: { color: "FECACA", width: 1 },
    rectRadius: 0.15,
  });
  s.addText("BEFORE", {
    x: 0.95, y: colY + 0.25, w: 5.5, h: 0.4,
    fontSize: 12, bold: true, color: RED, fontFace: "Calibri",
    charSpacing: 3,
  });
  s.addText([
    { text: "Manual review of every screenshot", options: { bullet: { code: "25CF" } } },
    { text: "Read each Order ID by eye, type-compare to form", options: { bullet: { code: "25CF" } } },
    { text: "Count stars one by one", options: { bullet: { code: "25CF" } } },
    { text: "No record of what was checked", options: { bullet: { code: "25CF" } } },
    { text: "Easy to make mistakes — hard to audit later", options: { bullet: { code: "25CF" } } },
  ], {
    x: 0.95, y: colY + 0.75, w: 5.5, h: colH - 0.9,
    fontSize: 15, color: INK, fontFace: "Calibri",
    paraSpaceAfter: 8,
  });

  // Now card
  s.addShape(pres.ShapeType.roundRect, {
    x: 6.85, y: colY, w: 5.78, h: colH,
    fill: { color: "F0FDF4" }, line: { color: "BBF7D0", width: 1 },
    rectRadius: 0.15,
  });
  s.addText("NOW", {
    x: 7.1, y: colY + 0.25, w: 5.3, h: 0.4,
    fontSize: 12, bold: true, color: GREEN, fontFace: "Calibri",
    charSpacing: 3,
  });
  s.addText([
    { text: "Every screenshot read automatically", options: { bullet: { code: "25CF" } } },
    { text: "Order IDs compared on the spot", options: { bullet: { code: "25CF" } } },
    { text: "Star counts detected by the system", options: { bullet: { code: "25CF" } } },
    { text: "All results saved and exportable", options: { bullet: { code: "25CF" } } },
    { text: "Hundreds of records in seconds", options: { bullet: { code: "25CF" } } },
  ], {
    x: 7.1, y: colY + 0.75, w: 5.3, h: colH - 0.9,
    fontSize: 15, color: INK, fontFace: "Calibri",
    paraSpaceAfter: 8,
  });

  addFooter(s, "Slide 3");
}

// =============================================================================
//  4 — DASHBOARD AT A GLANCE  (overview screenshot)
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Overview", "The dashboard at a glance");

  s.addText("Three areas, top to bottom — summary cards, filter toolbar, records table.", {
    x: 0.7, y: 1.7, w: 12, h: 0.4,
    fontSize: 16, color: MUTED, italic: true, fontFace: "Calibri",
  });

  s.addImage({
    path: path.join(SHOTS, "01_full_dashboard.png"),
    x: 1.6, y: 2.1, w: 10.0, h: 4.85,
    sizing: { type: "contain", w: 10.0, h: 4.85 },
  });

  // Section labels on right
  const labelX = 12.0;
  s.addText("Section 1", { x: labelX, y: 2.4,  w: 1.2, h: 0.35,
    fontSize: 11, bold: true, color: ACCENT, fontFace: "Calibri" });
  s.addText("Summary cards", { x: labelX, y: 2.7,  w: 1.3, h: 0.3,
    fontSize: 9,  color: MUTED, fontFace: "Calibri" });

  s.addText("Section 2", { x: labelX, y: 4.2,  w: 1.2, h: 0.35,
    fontSize: 11, bold: true, color: ACCENT, fontFace: "Calibri" });
  s.addText("Filters & search", { x: labelX, y: 4.5,  w: 1.3, h: 0.3,
    fontSize: 9,  color: MUTED, fontFace: "Calibri" });

  s.addText("Section 3", { x: labelX, y: 5.7,  w: 1.2, h: 0.35,
    fontSize: 11, bold: true, color: ACCENT, fontFace: "Calibri" });
  s.addText("Records table", { x: labelX, y: 6.0,  w: 1.3, h: 0.3,
    fontSize: 9,  color: MUTED, fontFace: "Calibri" });

  addFooter(s, "Slide 4");
}

// =============================================================================
//  5 — HEADER
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Header", "The title bar");

  s.addImage({
    path: path.join(SHOTS, "header.png"),
    x: 0.7, y: 2.0, w: 12.0, h: 1.2,
    sizing: { type: "contain", w: 12.0, h: 1.2 },
  });

  s.addText("Just a title bar — no data, no controls.", {
    x: 0.7, y: 3.6, w: 12.0, h: 0.5,
    fontSize: 18, color: INK, italic: true, fontFace: "Calibri",
    align: "center",
  });
  s.addText("Confirms which dashboard you are looking at.", {
    x: 0.7, y: 4.1, w: 12.0, h: 0.5,
    fontSize: 14, color: MUTED, fontFace: "Calibri",
    align: "center",
  });

  addFooter(s, "Slide 5");
}

// =============================================================================
//  6 — SECTION 1: METRIC CARDS  (full row)
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Section 1", "Summary cards");

  s.addImage({
    path: path.join(SHOTS, "metrics.png"),
    x: 0.5, y: 1.9, w: 12.3, h: 1.8,
    sizing: { type: "contain", w: 12.3, h: 1.8 },
  });

  s.addText("Five cards across the top give you the headline picture before you look at any individual record.", {
    x: 0.7, y: 3.95, w: 12.0, h: 0.5,
    fontSize: 14, color: MUTED, italic: true, fontFace: "Calibri",
    align: "center",
  });

  // 5 mini-cards below explaining each
  const blurbs = [
    ["In Pipeline",     "Total records loaded"],
    ["Pending",         "Still being processed"],
    ["Order ID Match",  "Match / Mismatch / Un-Verified"],
    ["Star Rating",     "≥ 4   |   < 4   |   Un-Verified"],
    ["Verified",        "YES / NO / Un-Verified"],
  ];
  const mW = 2.42, mH = 1.5, gap = 0.05;
  const startX = 0.5;
  blurbs.forEach(([t, b], i) => {
    const x = startX + i * (mW + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 4.8, w: mW, h: mH,
      fill: { color: SOFT_BG },
      line: { color: "E2E8F0", width: 1 },
      rectRadius: 0.08,
    });
    s.addText(t, {
      x: x + 0.1, y: 4.95, w: mW - 0.2, h: 0.5,
      fontSize: 13, bold: true, color: NAVY, fontFace: "Calibri",
      align: "center",
    });
    s.addText(b, {
      x: x + 0.1, y: 5.45, w: mW - 0.2, h: 0.8,
      fontSize: 11, color: MUTED, fontFace: "Calibri",
      align: "center",
    });
  });

  addFooter(s, "Slide 6");
}

// =============================================================================
//  7 — Order ID Match + Star Rating detail
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Section 1 · Detail", "Reading the result chips");

  // Left half — Order ID Match
  s.addText("Order ID Match", {
    x: 0.7, y: 1.95, w: 5.8, h: 0.5,
    fontSize: 22, bold: true, color: NAVY, fontFace: "Calibri",
  });

  const oidRows = [
    ["✓ Match",         "ID in screenshot = ID in form",                     GREEN],
    ["✕ Mismatch",      "The two IDs are different",                          RED],
    ["— Un-Verified",   "One of them could not be read",                       MUTED],
  ];
  oidRows.forEach(([chip, desc, color], i) => {
    const y = 2.55 + i * 0.75;
    s.addShape(pres.ShapeType.roundRect, {
      x: 0.7, y, w: 1.85, h: 0.55,
      fill: { color: color === GREEN ? "DCFCE7" : color === RED ? "FEE2E2" : "F1F5F9" },
      line: { color: color === GREEN ? "BBF7D0" : color === RED ? "FECACA" : "E2E8F0", width: 1 },
      rectRadius: 0.05,
    });
    s.addText(chip, {
      x: 0.7, y, w: 1.85, h: 0.55,
      fontSize: 14, bold: true, color, fontFace: "Calibri",
      align: "center", valign: "middle",
    });
    s.addText(desc, {
      x: 2.7, y, w: 3.8, h: 0.55,
      fontSize: 13, color: INK, fontFace: "Calibri", valign: "middle",
    });
  });

  // Right half — Star Rating
  s.addText("Star Rating", {
    x: 7.0, y: 1.95, w: 5.8, h: 0.5,
    fontSize: 22, bold: true, color: NAVY, fontFace: "Calibri",
  });
  const starRows = [
    ["★ ≥ 4",            "4 or 5 stars — positive review",   AMBER,  "FFFBEB", "FDE68A"],
    ["★ < 4",            "3 stars or less — negative",         MUTED,  "F1F5F9", "E2E8F0"],
    ["— Un-Verified",    "Stars could not be read",            MUTED,  "F1F5F9", "E2E8F0"],
  ];
  starRows.forEach(([chip, desc, color, fill, line], i) => {
    const y = 2.55 + i * 0.75;
    s.addShape(pres.ShapeType.roundRect, {
      x: 7.0, y, w: 1.85, h: 0.55,
      fill: { color: fill },
      line: { color: line, width: 1 },
      rectRadius: 0.05,
    });
    s.addText(chip, {
      x: 7.0, y, w: 1.85, h: 0.55,
      fontSize: 14, bold: true, color, fontFace: "Calibri",
      align: "center", valign: "middle",
    });
    s.addText(desc, {
      x: 9.0, y, w: 3.8, h: 0.55,
      fontSize: 13, color: INK, fontFace: "Calibri", valign: "middle",
    });
  });

  // Bottom — Verified
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 5.4, w: 12.0, h: 1.55,
    fill: { color: "EEF2FF" },
    line: { color: "C7D2FE", width: 1 },
    rectRadius: 0.1,
  });
  s.addText("Verified — the overall verdict", {
    x: 0.95, y: 5.55, w: 11.5, h: 0.4,
    fontSize: 16, bold: true, color: NAVY, fontFace: "Calibri",
  });
  s.addText([
    { text: "✓ YES ", options: { bold: true, color: GREEN } },
    { text: "= ID matched AND star rating is ≥ 4    ", options: { color: INK } },
    { text: "✕ NO ", options: { bold: true, color: RED } },
    { text: "= ID didn't match OR rating is < 4    ", options: { color: INK } },
    { text: "— Un-Verified ", options: { bold: true, color: MUTED } },
    { text: "= not enough info to decide", options: { color: INK } },
  ], {
    x: 0.95, y: 5.95, w: 11.5, h: 0.95,
    fontSize: 13, fontFace: "Calibri",
  });

  addFooter(s, "Slide 7");
}

// =============================================================================
//  8 — SECTION 2: FILTERS
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Section 2", "Filters & search");

  s.addImage({
    path: path.join(SHOTS, "filters.png"),
    x: 0.5, y: 1.9, w: 12.3, h: 1.4,
    sizing: { type: "contain", w: 12.3, h: 1.4 },
  });

  // 8 control descriptions in a 4×2 grid
  const controls = [
    ["🔍 Search",         "By file name, Order ID, or Ticket ID"],
    ["✦ Verified",        "Filter by overall verdict"],
    ["🔗 Order ID Match", "Filter by match result"],
    ["⭐ Star ≥ 4",       "Show only positive / negative / unreadable"],
    ["🏢 Branch",         "Filter by IFB branch"],
    ["📅 Date of Posting","Pick a date range"],
    ["⬇️ Export to CSV",  "Download the visible records"],
    ["✕ Clear",           "Reset every filter to defaults"],
  ];
  const cols = 4, gW = 3.05, gH = 1.4, gx = 0.5, gy = 3.6, gap = 0.08;
  controls.forEach(([title, desc], i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const x = gx + c * (gW + gap);
    const y = gy + r * (gH + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: gW, h: gH,
      fill: { color: SOFT_BG },
      line: { color: "E2E8F0", width: 1 },
      rectRadius: 0.08,
    });
    s.addText(title, {
      x: x + 0.15, y: y + 0.15, w: gW - 0.3, h: 0.45,
      fontSize: 14, bold: true, color: NAVY, fontFace: "Calibri",
    });
    s.addText(desc, {
      x: x + 0.15, y: y + 0.6, w: gW - 0.3, h: 0.75,
      fontSize: 11, color: MUTED, fontFace: "Calibri",
    });
  });

  addFooter(s, "Slide 8");
}

// =============================================================================
//  9 — SECTION 3: RECORDS TABLE  (screenshot + column legend left/right)
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Section 3", "Records table");

  s.addImage({
    path: path.join(SHOTS, "table.png"),
    x: 0.5, y: 1.9, w: 12.3, h: 2.5,
    sizing: { type: "contain", w: 12.3, h: 2.5 },
  });

  s.addText("One row per customer review. Use the columns below to read each record at a glance.", {
    x: 0.7, y: 4.55, w: 12.0, h: 0.4,
    fontSize: 14, color: MUTED, italic: true, fontFace: "Calibri",
    align: "center",
  });

  // 3-column legend of columns (selected highlights — full list on next slide)
  const legend = [
    ["Date of Posting", "When the review came in"],
    ["Zoho Order ID",   "ID typed by the customer"],
    ["File Order ID",   "ID read from the screenshot (red = differs)"],
    ["Service Rating",  "Stars on the \"Installation and Demo\" screen"],
    ["Product Rating",  "Stars on the \"Rate your experience\" screen"],
    ["Star Rating",     "Stars when neither label is detected"],
    ["Star ≥ 4",        "Yes if 4+ stars, No otherwise"],
    ["✦ Verified",      "Overall verdict (YES / NO / Un-Verified)"],
  ];
  const cols2 = 4, gW2 = 3.05, gH2 = 1.0, gx2 = 0.5, gy2 = 5.05, gap2 = 0.08;
  legend.forEach(([title, desc], i) => {
    const r = Math.floor(i / cols2), c = i % cols2;
    const x = gx2 + c * (gW2 + gap2);
    const y = gy2 + r * (gH2 + gap2);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: gW2, h: gH2,
      fill: { color: SOFT_BG },
      line: { color: "E2E8F0", width: 1 },
      rectRadius: 0.06,
    });
    s.addText(title, {
      x: x + 0.12, y: y + 0.08, w: gW2 - 0.24, h: 0.35,
      fontSize: 12, bold: true, color: NAVY, fontFace: "Calibri",
    });
    s.addText(desc, {
      x: x + 0.12, y: y + 0.4, w: gW2 - 0.24, h: 0.55,
      fontSize: 10, color: MUTED, fontFace: "Calibri",
    });
  });

  addFooter(s, "Slide 9");
}

// =============================================================================
//  10 — RED HIGHLIGHTING DETAIL
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Section 3 · Detail", "How differences are shown");

  s.addText("If the File Order ID does not exactly match the Zoho Order ID, the differing characters appear in red. Small differences are forgiven — they still count as a match.", {
    x: 0.7, y: 1.95, w: 12.0, h: 0.9,
    fontSize: 15, color: MUTED, italic: true, fontFace: "Calibri",
  });

  // 3 example rows
  const examples = [
    ["402-2799611-0609959", "402-2799611-0609959",                "✓ YES",   "No differences",                       GREEN],
    ["402-2799611-0609959", "402-2799611-060995",   "✓ YES",   "1 character missing — likely an OCR glitch",  GREEN, [16]],
    ["402-2799611-0609959", "402-2799611-0609959", "✓ YES",   "Identical — perfect match",                    GREEN],
  ];

  // Table-like layout
  // Headers
  const headers = ["Zoho Order ID", "File Order ID", "Order ID Match", "Why"];
  const colsX = [0.7, 4.2, 7.7, 9.4];
  const colsW = [3.4, 3.4, 1.6, 3.3];
  headers.forEach((h, i) => {
    s.addShape(pres.ShapeType.rect, {
      x: colsX[i], y: 3.0, w: colsW[i], h: 0.45,
      fill: { color: NAVY }, line: { color: NAVY, width: 0 },
    });
    s.addText(h, {
      x: colsX[i], y: 3.0, w: colsW[i], h: 0.45,
      fontSize: 12, bold: true, color: WHITE, fontFace: "Calibri",
      align: "center", valign: "middle",
    });
  });

  // Row 1 — Identical
  {
    const y = 3.5;
    s.addText("402-2799611-0609959", { x: colsX[0], y, w: colsW[0], h: 0.5,
      fontSize: 14, color: INK, fontFace: "Consolas", align: "center", valign: "middle" });
    s.addText("402-2799611-0609959", { x: colsX[1], y, w: colsW[1], h: 0.5,
      fontSize: 14, color: INK, fontFace: "Consolas", align: "center", valign: "middle" });
    s.addText("✓ YES", { x: colsX[2], y, w: colsW[2], h: 0.5,
      fontSize: 14, bold: true, color: GREEN, fontFace: "Calibri", align: "center", valign: "middle" });
    s.addText("Perfect match", { x: colsX[3], y, w: colsW[3], h: 0.5,
      fontSize: 12, color: MUTED, fontFace: "Calibri", valign: "middle" });
  }

  // Row 2 — 1-digit diff (red highlight)
  {
    const y = 4.05;
    s.addText("402-2799611-0609959", { x: colsX[0], y, w: colsW[0], h: 0.5,
      fontSize: 14, color: INK, fontFace: "Consolas", align: "center", valign: "middle" });
    s.addText([
      { text: "402-279961",  options: { color: INK, fontFace: "Consolas" } },
      { text: "5",           options: { color: RED, bold: true, fontFace: "Consolas" } },
      { text: "-0609959",    options: { color: INK, fontFace: "Consolas" } },
    ], { x: colsX[1], y, w: colsW[1], h: 0.5,
      fontSize: 14, align: "center", valign: "middle" });
    s.addText("✓ YES", { x: colsX[2], y, w: colsW[2], h: 0.5,
      fontSize: 14, bold: true, color: GREEN, fontFace: "Calibri", align: "center", valign: "middle" });
    s.addText("1 character off — forgiven", { x: colsX[3], y, w: colsW[3], h: 0.5,
      fontSize: 12, color: MUTED, fontFace: "Calibri", valign: "middle" });
  }

  // Row 3 — Many diffs
  {
    const y = 4.6;
    s.addText("402-2799611-0609959", { x: colsX[0], y, w: colsW[0], h: 0.5,
      fontSize: 14, color: INK, fontFace: "Consolas", align: "center", valign: "middle" });
    s.addText([
      { text: "402-", options: { color: INK, fontFace: "Consolas" } },
      { text: "3851230",  options: { color: RED, bold: true, fontFace: "Consolas" } },
      { text: "-0609959", options: { color: INK, fontFace: "Consolas" } },
    ], { x: colsX[1], y, w: colsW[1], h: 0.5,
      fontSize: 14, align: "center", valign: "middle" });
    s.addText("✕ NO", { x: colsX[2], y, w: colsW[2], h: 0.5,
      fontSize: 14, bold: true, color: RED, fontFace: "Calibri", align: "center", valign: "middle" });
    s.addText("Too many differences", { x: colsX[3], y, w: colsW[3], h: 0.5,
      fontSize: 12, color: MUTED, fontFace: "Calibri", valign: "middle" });
  }

  // Footnote
  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 5.7, w: 12.0, h: 1.0,
    fill: { color: "EEF2FF" }, line: { color: "C7D2FE", width: 1 },
    rectRadius: 0.1,
  });
  s.addText([
    { text: "Rule of thumb:  ", options: { bold: true, color: NAVY } },
    { text: "up to 3 differing characters are treated as a match (small OCR errors). ", options: { color: INK } },
    { text: "Four or more differences = different order.", options: { color: INK } },
  ], {
    x: 0.95, y: 5.85, w: 11.5, h: 0.75,
    fontSize: 14, fontFace: "Calibri", valign: "middle",
  });

  addFooter(s, "Slide 10");
}

// =============================================================================
//  11 — TYPICAL WORKFLOW
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addSectionHeader(s, "Workflow", "A typical session");

  const steps = [
    ["1", "Glance at the top",       "Read the five summary cards for the headline picture."],
    ["2", "Narrow it down",          "Pick filters: branch, date range, only failed verifications, etc."],
    ["3", "Read the table",          "Spot red-highlighted differences and check the verdicts."],
    ["4", "Export when needed",      "Click Export to CSV to share the filtered list."],
    ["5", "Start fresh",             "Hit Clear to wipe filters and start over."],
  ];

  const yStart = 2.0;
  const stepH  = 0.9;
  steps.forEach(([n, t, d], idx) => {
    const y = yStart + idx * (stepH + 0.15);
    // step number circle
    s.addShape(pres.ShapeType.ellipse, {
      x: 0.7, y, w: stepH, h: stepH,
      fill: { color: NAVY }, line: { color: NAVY, width: 0 },
    });
    s.addText(n, {
      x: 0.7, y, w: stepH, h: stepH,
      fontSize: 28, bold: true, color: WHITE,
      fontFace: "Calibri", align: "center", valign: "middle",
    });
    // body card
    s.addShape(pres.ShapeType.roundRect, {
      x: 1.85, y, w: 10.9, h: stepH,
      fill: { color: SOFT_BG }, line: { color: "E2E8F0", width: 1 },
      rectRadius: 0.08,
    });
    s.addText(t, {
      x: 2.05, y: y + 0.1, w: 10.6, h: 0.4,
      fontSize: 16, bold: true, color: NAVY, fontFace: "Calibri",
    });
    s.addText(d, {
      x: 2.05, y: y + 0.5, w: 10.6, h: 0.4,
      fontSize: 12, color: MUTED, fontFace: "Calibri",
    });
  });

  addFooter(s, "Slide 11");
}

// =============================================================================
//  12 — CLOSING
// =============================================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  s.addShape(pres.ShapeType.rect, {
    x: 0, y: 0, w: 0.4, h: H,
    fill: { color: ACCENT }, line: { color: ACCENT, width: 0 },
  });

  s.addText("That's the whole dashboard.", {
    x: 1.2, y: 2.5, w: 11, h: 1.0,
    fontSize: 44, bold: true, color: WHITE, fontFace: "Calibri",
  });

  s.addText("Five summary cards.   A filter toolbar.   A detailed table.", {
    x: 1.2, y: 3.6, w: 11, h: 0.6,
    fontSize: 22, color: ICE, fontFace: "Calibri",
  });

  s.addShape(pres.ShapeType.line, {
    x: 1.2, y: 4.4, w: 2.5, h: 0,
    line: { color: ACCENT, width: 3 },
  });

  s.addText("Thank you.", {
    x: 1.2, y: 4.7, w: 11, h: 0.7,
    fontSize: 28, italic: true, color: "9CB4D8", fontFace: "Calibri",
  });
}

// =============================================================================
pres.writeFile({ fileName: OUT }).then(() => {
  console.log("Wrote", OUT);
});
