/* ============================================================
   Citation Constellation — Client JS
   Handles search, SSE streaming, and result rendering
   ============================================================ */

// ── DOM refs ──────────────────────────────────────────────
const form           = document.getElementById('searchForm');
const paperInput     = document.getElementById('paperInput');
const searchBtn      = document.getElementById('searchBtn');
const btnText        = searchBtn.querySelector('.btn-text');
const btnSpinner     = searchBtn.querySelector('.btn-spinner');

const progressSec    = document.getElementById('progressSection');
const progressTitle  = document.getElementById('progressTitle');
const progressBar    = document.getElementById('progressBar');
const progressPct    = document.getElementById('progressPct');
const logPanel       = document.getElementById('logPanel');

const resultsSec     = document.getElementById('resultsSection');
const rootCard       = document.getElementById('rootCard');
const summaryStrip   = document.getElementById('summaryStrip');
const citationCards  = document.getElementById('citationCards');
const errorBanner    = document.getElementById('errorBanner');

// ── Starfield ─────────────────────────────────────────────
(function initStarfield() {
    const canvas = document.getElementById('starfield');
    const ctx    = canvas.getContext('2d');
    let stars    = [];

    function resize() {
        canvas.width  = window.innerWidth;
        canvas.height = window.innerHeight;
        stars = Array.from({length: 120}, () => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            r: Math.random() * 1.2 + .3,
            a: Math.random() * .6 + .15,
            d: Math.random() * .003 + .001,
            phase: Math.random() * Math.PI * 2,
        }));
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const t = performance.now() / 1000;
        for (const s of stars) {
            const alpha = s.a * (.6 + .4 * Math.sin(t * s.d * 200 + s.phase));
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(180,190,255,${alpha})`;
            ctx.fill();
        }
        requestAnimationFrame(draw);
    }

    window.addEventListener('resize', resize);
    resize();
    draw();
})();

// ── Helpers ───────────────────────────────────────────────
function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function setLoading(on) {
    searchBtn.disabled     = on;
    btnText.hidden         = on;
    btnSpinner.hidden      = !on;
    paperInput.readOnly    = on;
}

function resetUI() {
    progressSec.hidden     = true;
    resultsSec.hidden      = true;
    errorBanner.hidden     = true;
    summaryStrip.hidden    = true;
    logPanel.innerHTML     = '';
    citationCards.innerHTML = '';
    rootCard.innerHTML     = '';
    summaryStrip.innerHTML = '';
    progressBar.style.width = '0%';
    progressPct.textContent = '';
    progressTitle.textContent = 'Searching…';
}

function appendLog(msg) {
    const line = document.createElement('div');
    line.className = 'log-line' + (msg.startsWith('⚠') ? ' warn' : '');
    line.textContent = msg;
    logPanel.appendChild(line);
    logPanel.scrollTop = logPanel.scrollHeight;
}

function paperLink(p) {
    let links = '';
    if (p.arxiv_id) links += `<a href="https://arxiv.org/abs/${esc(p.arxiv_id)}" target="_blank" rel="noopener">arXiv</a>`;
    if (p.doi)      links += `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a>`;
    if (p.bibcode)  links += `<a href="https://ui.adsabs.harvard.edu/abs/${esc(p.bibcode)}/abstract" target="_blank" rel="noopener">ADS</a>`;
    return links;
}

// ── Render root card ──────────────────────────────────────
function renderRoot(p) {
    const authorsStr = p.authors.join(', ') + (p.authors_truncated ? ' …' : '');
    rootCard.innerHTML = `
        <span class="tag">Target Paper</span>
        <div class="paper-title">${esc(p.title)}</div>
        <div class="paper-meta">${esc(authorsStr)}</div>
        <div class="paper-meta">${p.year || ''}</div>
        <div class="paper-links">${paperLink(p)}</div>
    `;
}

// ── Render single citation card ───────────────────────────
function renderCiteCard(item) {
    const p = item.paper;
    const authorsStr = p.authors.join(', ') + (p.authors_truncated ? ' …' : '');
    const ctxHtml = item.citations.map(c => {
        if (c.type === 'status') {
            return `<span class="ctx-pill status-pill"><span class="dot"></span>${esc(c.text)}</span>`;
        }
        return `<span class="ctx-pill"><span class="dot"></span>${esc(c.label)}</span>`;
    }).join('');

    const card = document.createElement('div');
    card.className = 'cite-card';
    card.innerHTML = `
        <div class="card-header">
            <div class="paper-title">${esc(p.title)}</div>
            ${p.year ? `<span class="year-badge">${p.year}</span>` : ''}
        </div>
        <div class="authors">${esc(authorsStr)}</div>
        <div class="links">${paperLink(p)}</div>
        <div class="context-list">${ctxHtml}</div>
    `;
    citationCards.appendChild(card);
}

// ── Render summary ────────────────────────────────────────
function renderSummary(citations) {
    const total = citations.length;
    const withCtx = citations.filter(c =>
        c.citations.some(x => x.type === 'context')
    ).length;

    // Count unique sections
    const sections = new Set();
    for (const c of citations) {
        for (const x of c.citations) {
            if (x.type === 'context' && x.section) sections.add(x.section);
        }
    }

    summaryStrip.innerHTML = `
        <div class="summary-stat"><div class="num">${total}</div><div class="label">Citing Papers</div></div>
        <div class="summary-stat"><div class="num">${withCtx}</div><div class="label">With Context</div></div>
        <div class="summary-stat"><div class="num">${sections.size}</div><div class="label">Unique Sections</div></div>
    `;
    summaryStrip.hidden = false;
}

// ── Search handler ────────────────────────────────────────
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = paperInput.value.trim();
    if (!input) return;

    resetUI();
    setLoading(true);
    progressSec.hidden = false;

    try {
        // Start job
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                input,
                keep_sources: document.getElementById('keepSources').checked,
            }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Server error');
        }

        const {job_id} = await res.json();

        // SSE stream
        const evtSrc = new EventSource(`/api/stream/${job_id}`);

        evtSrc.addEventListener('log', (e) => {
            appendLog(JSON.parse(e.data));
        });

        evtSrc.addEventListener('root', (e) => {
            const p = JSON.parse(e.data);
            resultsSec.hidden = false;
            renderRoot(p);
        });

        evtSrc.addEventListener('total', (e) => {
            // just informational
        });

        evtSrc.addEventListener('progress', (e) => {
            const d = JSON.parse(e.data);
            const pct = Math.round((d.current / d.total) * 100);
            progressBar.style.width = pct + '%';
            progressPct.textContent = `${d.current}/${d.total}`;
            progressTitle.textContent = `Processing citations… (${d.current}/${d.total})`;
        });

        evtSrc.addEventListener('done', (e) => {
            evtSrc.close();
            const data = JSON.parse(e.data);
            progressTitle.textContent = 'Done!';
            progressBar.style.width = '100%';

            resultsSec.hidden = false;
            renderRoot(data.root);
            renderSummary(data.citations);
            for (const c of data.citations) renderCiteCard(c);

            setLoading(false);
        });

        evtSrc.addEventListener('error', (e) => {
            // SSE 'error' can fire for both custom events and connection drops
            try {
                const d = JSON.parse(e.data);
                showError(d.message);
            } catch {
                showError('Connection to server lost.');
            }
            evtSrc.close();
            setLoading(false);
        });

    } catch (err) {
        showError(err.message);
        setLoading(false);
    }
});

function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.hidden = false;
}
