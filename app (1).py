import streamlit as st
import sqlite3
import re
import io
import textwrap
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "lecture_notes.db"

st.set_page_config(
    page_title="Smart Lecture Notes Maker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Styling ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --purple:#6D45D8; --violet:#8B5CF6; --ink:#241B3A; --muted:#756D86; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:linear-gradient(180deg,#FBFAFF 0%,#F6F2FF 100%); color:var(--ink); }
.block-container { max-width:1120px; padding-top:1.2rem; padding-bottom:3rem; }
h1,h2,h3 { font-family:'Manrope',sans-serif !important; color:#241B3A; letter-spacing:-.03em; }
.hero { background:linear-gradient(120deg,#34205F 0%,#6742C8 55%,#9469EE 100%);
 color:white; padding:2.3rem 2.1rem; border-radius:24px; box-shadow:0 18px 50px #51339a26; }
.hero h1 {color:white !important; font-size:clamp(2rem,5vw,3.1rem); line-height:1.12; margin:.5rem 0;}
.hero p {color:#EEE8FF; font-size:1.05rem; max-width:650px;}
.eyebrow {color:#D8C9FF; font-weight:700; text-transform:uppercase; letter-spacing:.14em; font-size:.75rem;}
.feature {background:white; border:1px solid #EEE8FA; border-radius:18px; padding:1.1rem; min-height:140px; box-shadow:0 6px 22px #3b21650a;}
.feature .emoji {font-size:1.5rem;}
.feature h3 {font-size:1rem; margin:.45rem 0 .25rem;}
.feature p {color:#766D86; font-size:.9rem; margin:0;}
.metric {background:white;border:1px solid #EEE8FA;border-radius:16px;padding:1rem 1.1rem;}
.metric .num {font-family:'Manrope';font-weight:800;font-size:1.8rem;color:#6D45D8;}
.metric .lbl {font-size:.82rem;color:#756D86;}
.section-kicker {color:#7652CC;font-size:.75rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;}
div.stButton > button, div.stDownloadButton > button, button[kind="primary"] {
 border-radius:12px; border:0; font-weight:700; min-height:2.8rem;
 background:linear-gradient(100deg,#6742C8,#8A5CE6); color:white;
}
div.stButton > button:hover, div.stDownloadButton > button:hover {background:linear-gradient(100deg,#5532B3,#7546D3); color:white; border:0;}
div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stSelectbox"] div[role="combobox"] {
 border-radius:12px; border-color:#E4DDF2; background:white;
}
div[data-testid="stTabs"] button {font-weight:700;}
.note-card {background:white;border:1px solid #EEE8FA;border-radius:16px;padding:1rem;margin:.45rem 0;}
.small-muted {color:#7B728B;font-size:.85rem;}
hr {border-color:#EEE8FA;}
footer {visibility:hidden;}
@media(max-width:640px) {
 .block-container {padding-left:1rem;padding-right:1rem;}
 .hero {padding:1.5rem 1.2rem;border-radius:18px;}
}
</style>
""", unsafe_allow_html=True)

# ---------- Database ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, subject TEXT NOT NULL, method TEXT NOT NULL,
            content TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        conn.commit()

init_db()

def all_notes(search=""):
    with get_conn() as conn:
        if search:
            q = f"%{search.strip()}%"
            rows = conn.execute("""SELECT * FROM notes
                WHERE title LIKE ? OR subject LIKE ? OR content LIKE ?
                ORDER BY id DESC""", (q,q,q)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

def save_note(title, subject, method, content):
    with get_conn() as conn:
        conn.execute("INSERT INTO notes(title,subject,method,content,created_at) VALUES(?,?,?,?,?)",
                     (title, subject, method, content, datetime.now().strftime("%d %b %Y, %I:%M %p")))
        conn.commit()

def update_note(note_id, title, subject, method, content):
    with get_conn() as conn:
        conn.execute("UPDATE notes SET title=?,subject=?,method=?,content=? WHERE id=?",
                     (title,subject,method,content,note_id))
        conn.commit()

def delete_note(note_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        conn.commit()

# ---------- Content-aware note generation ----------
def clean_lines(text):
    lines = [re.sub(r'\s+', ' ', x).strip(" •\\t-") for x in text.splitlines()]
    return [x for x in lines if x]

def split_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', text)) if len(s.strip()) > 18]

def extract_definitions(text):
    patterns = [
        r'([^.!?\n]{2,90}?)\s+(?:is defined as|is|are|refers to|means)\s+([^.!?\n]{8,180})',
        r'([^.!?\n]{2,90}?)\s*:\s*([^.!?\n]{8,180})'
    ]
    found = []
    for pat in patterns:
        for a,b in re.findall(pat, text, flags=re.I):
            item = (a.strip(" -•"), b.strip())
            if len(item[0].split()) <= 10 and item not in found:
                found.append(item)
    return found[:8]

def make_outline(text):
    lines = clean_lines(text)
    sentences = split_sentences(text)
    # Preserve meaningful short standalone lines as likely headings.
    headings = [x for x in lines if len(x.split()) <= 8 and not x.endswith(('.', '?')) and len(x) > 2]
    points = [s for s in sentences if not any(s.lower().startswith(h.lower()) for h in headings)]
    if not points:
        points = sentences or [text.strip()]
    # Choose key points using signal words and sentence length, with source order retained.
    signals = ('important','therefore','because','however','includes','consists','such as',
               'for example','first','second','finally','advantages','disadvantages','process',
               'function','used to','results in','known as')
    ranked = sorted(enumerate(points), key=lambda z: (sum(w in z[1].lower() for w in signals), min(len(z[1]),220)), reverse=True)
    key = [s for _,s in ranked[:min(7,len(ranked))]]
    key_set = set(key)
    summary_sentences = points[:min(3,len(points))]
    defs = extract_definitions(text)
    questions = []
    for h in headings[:4]:
        questions.append(f"What is {h.rstrip(':')}?")
    for term, definition in defs[:3]:
        questions.append(f"Explain {term}.")
    for s in key[:3]:
        words = re.findall(r'[A-Za-z][A-Za-z-]+', s)
        topic = " ".join(words[:5]) if words else "this concept"
        questions.append(f"Why is {topic} important?")
    if not questions:
        questions = ["What are the main ideas in this lecture?", "Explain the most important concept in your own words."]
    return headings, points, key, summary_sentences, defs, list(dict.fromkeys(questions))[:8]

def generate_notes(title, subject, source, method):
    headings, points, key, summary, defs, questions = make_outline(source)
    title = title.strip()
    subject = subject.strip()
    out = [f"# {title}", f"**Subject:** {subject}", f"**Method:** {method}", ""]
    if method == "Cornell Method":
        out += ["## Cue / Questions", *[f"- {q}" for q in questions[:6]], "",
                "## Notes", *[f"- {p}" for p in points[:8]], "",
                "## Summary", " ".join(summary)]
    elif method == "Outline Method":
        out += ["## Main headings"]
        if headings:
            for h in headings[:8]:
                out.append(f"### {h}")
                related = [p for p in points if h.lower().split()[0] in p.lower()] if h.split() else []
                for p in (related[:3] or points[:2]):
                    out.append(f"- {p}")
        else:
            out += ["### Core concepts"] + [f"- {p}" for p in points[:8]]
        out += ["", "## Key points"] + [f"- {p}" for p in key]
    elif method == "Mind Mapping":
        out += [f"## Central topic: {title}", "```text", title]
        for i, h in enumerate(headings[:6] or ["Key ideas"]):
            out.append(f"├── {h}")
            related = [p for p in points if h.lower().split()[0] in p.lower()] if h.split() else []
            for p in (related[:2] or points[i*2:(i*2)+2]):
                out.append(f"│   └── {p}")
        out += ["```", "", "## Supporting details"] + [f"- {p}" for p in key]
    else:  # Chart Method
        out += ["## Concept chart", "| Topic / concept | Explanation from lecture |", "|---|---|"]
        concepts = headings[:6] or [f"Key idea {i+1}" for i in range(min(6,len(points)))]
        for i, h in enumerate(concepts):
            related = [p for p in points if h.lower().split()[0] in p.lower()] if h.split() else []
            detail = (related or points[i:i+1] or ["Review this concept in the source"])[0].replace("|","/")
            out.append(f"| {h.replace('|','/')} | {detail} |")
        out += ["", "## Important points"] + [f"- {p}" for p in key]
    out += ["", "## Key definitions"]
    if defs:
        out += [f"- **{a}:** {b}" for a,b in defs]
    else:
        out += ["- No explicit definition pattern was detected. Review key terms in the lecture text."]
    out += ["", "## Short summary", " ".join(summary) if summary else "Review the key points above."]
    out += ["", "## Revision questions"] + [f"{i+1}. {q}" for i,q in enumerate(questions)]
    out += ["", "---", "*Generated from the lecture text you provided. Check and edit the notes before studying.*"]
    return "\n".join(out)

def make_summary(source):
    sentences = split_sentences(source)
    if not sentences:
        return source.strip()[:600]
    return " ".join(sentences[:min(3,len(sentences))])

def make_revision_questions(source):
    return make_outline(source)[-1]

def pdf_bytes(text, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="NoteTitle", parent=styles["Title"], textColor=colors.HexColor("#5532A8"), spaceAfter=12))
    styles.add(ParagraphStyle(name="NoteBody", parent=styles["BodyText"], leading=15, spaceAfter=6))
    story = [Paragraph(title.replace("&","&amp;"), styles["NoteTitle"]), Spacer(1,6)]
    for line in text.splitlines():
        safe = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        if line.startswith("# "):
            story.append(Paragraph(safe[2:], styles["Heading1"]))
        elif line.startswith("## "):
            story.append(Paragraph(safe[3:], styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(safe[4:], styles["Heading3"]))
        elif line.strip().startswith("|") or line.strip().startswith("```"):
            story.append(Preformatted(line, styles["Code"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + safe[2:], styles["NoteBody"]))
        elif re.match(r'^\d+\.', line):
            story.append(Paragraph(safe, styles["NoteBody"]))
        elif line.strip():
            story.append(Paragraph(safe.replace("**",""), styles["NoteBody"]))
        else:
            story.append(Spacer(1,4))
    doc.build(story)
    return buffer.getvalue()

# ---------- Navigation ----------
if "page" not in st.session_state:
    st.session_state.page = "Home"
if "generated" not in st.session_state:
    st.session_state.generated = ""
if "source_text" not in st.session_state:
    st.session_state.source_text = ""
if "gen_title" not in st.session_state:
    st.session_state.gen_title = ""
if "gen_subject" not in st.session_state:
    st.session_state.gen_subject = "General"

with st.sidebar:
    st.markdown("## 📚 Smart Notes")
    st.caption("Your lecture-to-revision workspace")
    pages = ["Home", "Create Notes", "My Notes", "Dashboard", "How It Works"]
    for p in pages:
        if st.button(("✦  " if st.session_state.page == p else "") + p, key="nav_"+p, use_container_width=True):
            st.session_state.page = p
            st.rerun()
    st.divider()
    st.caption("Made for focused learning • Works offline after setup")

def go(page):
    st.session_state.page = page
    st.rerun()

# ---------- Home ----------
if st.session_state.page == "Home":
    st.markdown("""
    <div class="hero">
      <div class="eyebrow">✦ Your smarter study companion</div>
      <h1>Turn Every Lecture<br>into Smart Notes.</h1>
      <p>Transform your class notes and lecture text into clear, organized, easy-to-revise study material — using a method that works for you.</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")
    c1,c2 = st.columns([1,1])
    with c1:
        if st.button("✦  Start Making Notes", type="primary", use_container_width=True):
            go("Create Notes")
    with c2:
        if st.button("View My Saved Notes  →", use_container_width=True):
            go("My Notes")
    st.write("")
    st.markdown('<div class="section-kicker">Everything you need to study smarter</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    features = [("🧠","Content-based notes","Organize the actual lecture text you paste — not generic sample content."),
                ("🗂️","Four study methods","Choose Cornell, Outline, Mind Mapping or Chart format."),
                ("📥","Save & export","Keep notes on your device, search them, edit and download as TXT or PDF.")]
    for col,(emoji,title,desc) in zip(cols,features):
        with col:
            st.markdown(f'<div class="feature"><div class="emoji">{emoji}</div><h3>{title}</h3><p>{desc}</p></div>',unsafe_allow_html=True)
    st.write("")
    st.markdown('<div class="section-kicker">A simple five-step workflow</div>', unsafe_allow_html=True)
    steps = st.columns(5)
    for col,(n,t) in zip(steps,[("01","Paste lecture"),("02","Choose method"),("03","Generate"),("04","Edit & save"),("05","Revise")]):
        with col:
            st.markdown(f'<div class="metric"><div class="num">{n}</div><div class="lbl">{t}</div></div>',unsafe_allow_html=True)

# ---------- Create Notes ----------
elif st.session_state.page == "Create Notes":
    st.markdown("## ✦ Smart Notes Generator")
    st.caption("Paste your lecture material and create a structured first draft in seconds.")
    with st.form("generator_form"):
        col1,col2 = st.columns(2)
        with col1:
            title = st.text_input("Lecture title *", value=st.session_state.gen_title, placeholder="e.g. Introduction to Data Structures")
        with col2:
            subject = st.text_input("Subject name *", value=st.session_state.gen_subject, placeholder="e.g. Programming in C")
        method = st.selectbox("Choose your note-making method", ["Cornell Method","Outline Method","Mind Mapping","Chart Method"])
        lecture = st.text_area("Lecture content *", value=st.session_state.source_text,
            height=260, placeholder="Paste your lecture transcript, class notes or textbook extract here...\n\nTip: Include headings and definitions when available.")
        submitted = st.form_submit_button("✦ Generate Smart Notes", type="primary", use_container_width=True)
    if submitted:
        if not title.strip() or not subject.strip() or not lecture.strip():
            st.error("Please enter a lecture title, subject and lecture content.")
        elif len(lecture.strip()) < 60:
            st.warning("Please add a little more lecture content (at least 60 characters) for useful notes.")
        else:
            st.session_state.gen_title = title.strip()
            st.session_state.gen_subject = subject.strip()
            st.session_state.source_text = lecture.strip()
            st.session_state.generated = generate_notes(title,subject,lecture,method)
            st.session_state.gen_method = method
            st.success("Your notes are ready. Review and edit them below.")
    if st.session_state.generated:
        st.divider()
        st.markdown("### Your generated notes")
        st.caption("You can edit this draft directly before saving or downloading.")
        edited = st.text_area("Edit your notes", value=st.session_state.generated, height=420, key="editable_notes")
        a,b,c = st.columns(3)
        with a:
            if st.button("Save to My Notes", type="primary", use_container_width=True):
                save_note(st.session_state.gen_title,st.session_state.gen_subject,
                          getattr(st.session_state,"gen_method","Outline Method"),edited)
                st.success("Saved to My Notes.")
        with b:
            st.download_button("⬇ Download TXT", data=edited.encode("utf-8"),
                file_name=re.sub(r'[^a-zA-Z0-9_-]+','_',st.session_state.gen_title) + ".txt",
                mime="text/plain", use_container_width=True)
        with c:
            try:
                pdf_data = pdf_bytes(edited,st.session_state.gen_title)
                st.download_button("⬇ Download PDF", data=pdf_data,
                    file_name="smart_notes.pdf", mime="application/pdf", use_container_width=True)
            except Exception as e:
                st.error(f"PDF export is unavailable: {e}")
        d,e = st.columns(2)
        with d:
            if st.button("Copy notes", use_container_width=True):
                st.code(edited, language=None)
                st.info("Select the text above and use your phone/browser's Copy command. Streamlit clipboard access varies by browser.")
        with e:
            if st.button("Create another note", use_container_width=True):
                st.session_state.generated = ""
                st.rerun()
        st.markdown("#### Quick revision tools")
        x,y = st.columns(2)
        with x:
            if st.button("Show short summary", use_container_width=True):
                st.info(make_summary(st.session_state.source_text))
        with y:
            if st.button("Show revision questions", use_container_width=True):
                for i,q in enumerate(make_revision_questions(st.session_state.source_text),1):
                    st.write(f"{i}. {q}")

# ---------- My Notes ----------
elif st.session_state.page == "My Notes":
    st.markdown("## 🗂️ My Saved Notes")
    search = st.text_input("Search by title, subject or note content", placeholder="Type to search...")
    notes = all_notes(search)
    if not notes:
        st.info("No saved notes found. Create your first note to see it here.")
        if st.button("Create notes now", type="primary"):
            go("Create Notes")
    else:
        st.caption(f"{len(notes)} note(s) found")
        for note in notes:
            with st.expander(f"📘 {note['title']}  ·  {note['subject']}  ·  {note['created_at']}"):
                st.caption(f"Method: {note['method']}  |  Note ID: {note['id']}")
                edited_saved = st.text_area("Note content", value=note["content"], height=260, key=f"saved_{note['id']}")
                col1,col2,col3 = st.columns(3)
                with col1:
                    if st.button("Update note", key=f"update_{note['id']}", use_container_width=True):
                        update_note(note["id"],note["title"],note["subject"],note["method"],edited_saved)
                        st.success("Note updated.")
                        st.rerun()
                with col2:
                    st.download_button("Download TXT", data=edited_saved.encode("utf-8"),
                        file_name=f"note_{note['id']}.txt", mime="text/plain",
                        key=f"txt_{note['id']}", use_container_width=True)
                with col3:
                    if st.button("Delete", key=f"delete_{note['id']}", use_container_width=True):
                        delete_note(note["id"])
                        st.success("Note deleted.")
                        st.rerun()
                try:
                    st.download_button("Download PDF", data=pdf_bytes(edited_saved,note["title"]),
                        file_name=f"note_{note['id']}.pdf", mime="application/pdf",
                        key=f"pdf_{note['id']}")
                except Exception:
                    st.warning("PDF export unavailable. TXT download still works.")

# ---------- Dashboard ----------
elif st.session_state.page == "Dashboard":
    st.markdown("## 📊 Student Dashboard")
    notes = all_notes()
    subjects = {}
    for n in notes:
        subjects[n["subject"]] = subjects.get(n["subject"],0)+1
    recent = notes[:5]
    m1,m2,m3 = st.columns(3)
    with m1: st.markdown(f'<div class="metric"><div class="num">{len(notes)}</div><div class="lbl">Total notes created</div></div>',unsafe_allow_html=True)
    with m2: st.markdown(f'<div class="metric"><div class="num">{len(subjects)}</div><div class="lbl">Subjects covered</div></div>',unsafe_allow_html=True)
    with m3: st.markdown(f'<div class="metric"><div class="num">{len(recent)}</div><div class="lbl">Recent notes shown</div></div>',unsafe_allow_html=True)
    st.write("")
    left,right = st.columns([1.2,1])
    with left:
        st.markdown("### Recently saved")
        if recent:
            for n in recent:
                st.markdown(f'<div class="note-card"><b>📘 {n["title"]}</b><br><span class="small-muted">{n["subject"]} · {n["created_at"]}</span></div>',unsafe_allow_html=True)
        else:
            st.info("Your saved notes will appear here.")
    with right:
        st.markdown("### Subject-wise notes")
        if subjects:
            for s,count in sorted(subjects.items(),key=lambda x:x[1],reverse=True):
                st.write(f"**{s}**")
                st.progress(count/max(subjects.values()))
                st.caption(f"{count} note(s)")
        else:
            st.info("No subject data yet.")
    if st.button("＋ Create a new note", type="primary", use_container_width=True):
        go("Create Notes")

# ---------- How it works ----------
elif st.session_state.page == "How It Works":
    st.markdown("## How It Works")
    st.caption("A straightforward workflow from raw lecture material to revision-ready notes.")
    process = [
        ("01","Enter or paste lecture content","Add a title, subject and your own lecture transcript, classroom notes or study material."),
        ("02","Select a note-making method","Pick Cornell, Outline, Mind Mapping or Chart Method to match your learning style."),
        ("03","Generate organized notes","The built-in text processor identifies likely headings, key points, definitions, summaries and revision prompts from the content you entered."),
        ("04","Edit and save","Review the draft, correct anything needed, then save it to your local notes database."),
        ("05","Revise and download","Search saved notes, revisit revision questions, and export your notes as TXT or PDF.")
    ]
    for n,title,desc in process:
        st.markdown(f'<div class="note-card"><span class="section-kicker">STEP {n}</span><h3 style="margin:.3rem 0">{title}</h3><span class="small-muted">{desc}</span></div>',unsafe_allow_html=True)
    st.warning("Transparency note: this project uses local rule-based text processing. It does not call an AI service or claim to understand content like a connected AI model. The generated draft is based on the text you provide and should be checked before exams.")
    st.markdown("### Note-making methods")
    st.write("- **Cornell:** cue questions, lecture notes and a summary.")
    st.write("- **Outline:** nested headings and supporting bullet points.")
    st.write("- **Mind Mapping:** a central topic with branches and supporting details.")
    st.write("- **Chart:** concepts arranged in a comparison table.")

st.divider()
st.markdown("<div style='text-align:center;color:#8B829A;font-size:.8rem'>Smart Lecture Notes Maker · Built for student learning</div>", unsafe_allow_html=True)
