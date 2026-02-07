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
const paperModal     = document.getElementById('paperModal');

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

// ── Paper Detail Modal ────────────────────────────────────
function openPaperModal(paperData) {
    // Populate title
    document.getElementById('modalTitle').textContent = paperData.title || 'Unknown Title';

    // Populate authors
    const authorsText = paperData.authors && paperData.authors.length > 0
        ? paperData.authors.join(', ')
        : 'Unknown authors';
    document.getElementById('modalAuthors').textContent = authorsText;

    // Populate abstract
    const abstractEl = document.getElementById('modalAbstract');
    if (paperData.abstract) {
        abstractEl.textContent = paperData.abstract;
        abstractEl.style.fontStyle = 'normal';
    } else {
        abstractEl.textContent = 'No abstract available.';
        abstractEl.style.fontStyle = 'italic';
    }

    // Populate links
    const linksEl = document.getElementById('modalLinks');
    linksEl.innerHTML = '';

    if (paperData.arxiv_id) {
        const arxivLink = document.createElement('a');
        arxivLink.href = `https://arxiv.org/abs/${paperData.arxiv_id}`;
        arxivLink.target = '_blank';
        arxivLink.textContent = '📄 arXiv';
        linksEl.appendChild(arxivLink);
    }

    if (paperData.doi) {
        const doiLink = document.createElement('a');
        doiLink.href = `https://doi.org/${paperData.doi}`;
        doiLink.target = '_blank';
        doiLink.textContent = '🔗 DOI';
        linksEl.appendChild(doiLink);
    }

    if (paperData.bibcode) {
        const adsLink = document.createElement('a');
        adsLink.href = `https://ui.adsabs.harvard.edu/abs/${paperData.bibcode}`;
        adsLink.target = '_blank';
        adsLink.textContent = '🔭 ADS';
        linksEl.appendChild(adsLink);
    }

    if (paperData.openalex_id) {
        const openalexLink = document.createElement('a');
        openalexLink.href = paperData.openalex_id;
        openalexLink.target = '_blank';
        openalexLink.textContent = '🌐 OpenAlex';
        linksEl.appendChild(openalexLink);
    }

    // Populate topics if available
    const topicsSection = document.getElementById('modalTopicsSection');
    const topicsEl = document.getElementById('modalTopics');
    if (paperData.topics && paperData.topics.length > 0) {
        topicsSection.hidden = false;
        topicsEl.innerHTML = paperData.topics.map(t =>
            `<span class="topic-badge">${esc(t.display_name)}</span>`
        ).join(' ');
    } else {
        topicsSection.hidden = true;
    }

    // Show modal
    paperModal.showModal();
}

// Modal close handler
paperModal.addEventListener('click', (e) => {
    if (e.target === paperModal || e.target.classList.contains('modal-close')) {
        paperModal.close();
    }
});

// ── Render root card ──────────────────────────────────────
function renderRoot(p) {
    const authorsStr = p.authors.join(', ') + (p.authors_truncated ? ' …' : '');

    let topicsHTML = '';
    if (p.topics && p.topics.length > 0) {
        const topicTags = p.topics.slice(0, 3).map(t =>
            `<span class="topic-badge">${esc(t.display_name)}</span>`
        ).join('');
        topicsHTML = `<div class="topics">${topicTags}</div>`;
    }

    rootCard.innerHTML = `
        <span class="tag">Target Paper</span>
        <div class="paper-title">${esc(p.title)}</div>
        <div class="paper-meta">${esc(authorsStr)}</div>
        <div class="paper-meta">${p.year || ''}</div>
        ${topicsHTML}
        <div class="paper-links">${paperLink(p)}</div>
    `;

    // Add click handler to open modal
    rootCard.addEventListener('click', () => {
        openPaperModal(p);
    });
}

// ── Render single citation card ───────────────────────────
function renderCiteCard(item) {
    const p = item.paper;

    // Build author string with highlighting for shared authors
    let authorsHTML = '';
    for (let i = 0; i < p.authors.length; i++) {
        const author = p.authors[i];
        const isShared = p.shared_authors && p.shared_authors.includes(author);

        if (isShared) {
            authorsHTML += `<span class="shared-author" title="Also author of target paper">${esc(author)}</span>`;
        } else {
            authorsHTML += esc(author);
        }

        if (i < p.authors.length - 1) {
            authorsHTML += ', ';
        }
    }

    if (p.authors_truncated) {
        authorsHTML += ' …';
    }

    const ctxHtml = item.citations.map(c => {
        if (c.type === 'status') {
            return `<span class="ctx-pill status-pill"><span class="dot"></span>${esc(c.text)}</span>`;
        }
        return `<span class="ctx-pill"><span class="dot"></span>${esc(c.label)}</span>`;
    }).join('');

    let topicsHTML = '';
    if (p.topics && p.topics.length > 0) {
        const topicTags = p.topics.slice(0, 3).map(t =>
            `<span class="topic-badge">${esc(t.display_name)}</span>`
        ).join('');
        topicsHTML = `<div class="topics">${topicTags}</div>`;
    }

    const card = document.createElement('div');
    card.className = 'cite-card' + (p.has_shared_authors ? ' has-shared-authors' : '');
    card.innerHTML = `
        <div class="card-header">
            <div class="paper-title">${esc(p.title)}</div>
            ${p.year ? `<span class="year-badge">${p.year}</span>` : ''}
            ${p.has_shared_authors ? '<span class="shared-badge" title="Shares authors with target">⭐ Shared</span>' : ''}
        </div>
        <div class="authors">${authorsHTML}</div>
        ${topicsHTML}
        <div class="links">${paperLink(p)}</div>
        <div class="context-list">${ctxHtml}</div>
    `;

    // Add click handler to open modal (but not if clicking links)
    card.addEventListener('click', (e) => {
        if (e.target.tagName === 'A') return;
        openPaperModal(p);
    });

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
    progressTitle.textContent = 'Fetching keywords from all citing papers…';
    progressBar.style.width = '25%';

    try {
        // Fetch all keywords first
        const keywordRes = await fetch('/api/get_keywords', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                input,
                source: document.getElementById('sourceSelect').value,
            }),
        });

        if (!keywordRes.ok) {
            const err = await keywordRes.json();
            throw new Error(err.error || 'Failed to fetch keywords');
        }

        const keywordData = await keywordRes.json();

        // Show keyword selection panel
        showKeywordSelection(input, keywordData);

        setLoading(false);
        progressSec.hidden = true;

    } catch (err) {
        showError(err.message);
        setLoading(false);
    }
});

// ── Show keyword selection UI ──────────────────────────────
function showKeywordSelection(input, keywordData) {
    const keywordsSection = document.getElementById('keywordsSection');
    const keywordsList = document.getElementById('keywordsList');
    const totalPapersCount = document.getElementById('totalPapersCount');

    totalPapersCount.textContent = keywordData.total_papers;

    // Clear and populate keywords list
    keywordsList.innerHTML = '';

    if (keywordData.keywords.length === 0) {
        keywordsList.innerHTML = '<p style="color: var(--text-muted);">No keywords found in citing papers.</p>';
    } else {
        keywordData.keywords.forEach(({keyword, count}) => {
            const item = document.createElement('label');
            item.className = 'keyword-item';
            item.innerHTML = `
                <input type="checkbox" value="${esc(keyword)}">
                <span>${esc(keyword)}<span class="keyword-count">(${count})</span></span>
            `;
            keywordsList.appendChild(item);
        });
    }

    keywordsSection.hidden = false;

    // Handle Select All
    document.getElementById('selectAllBtn').onclick = () => {
        keywordsList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
        });
    };

    // Handle Select None
    document.getElementById('selectNoneBtn').onclick = () => {
        keywordsList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
    };

    // Handle Process Selected
    document.getElementById('processBtn').onclick = async () => {
        const selectedKeywords = Array.from(
            keywordsList.querySelectorAll('input[type="checkbox"]:checked')
        ).map(cb => cb.value);

        if (selectedKeywords.length === 0) {
            showError('Please select at least one keyword');
            return;
        }

        // Hide keyword panel, show progress
        keywordsSection.hidden = true;
        progressSec.hidden = false;
        setLoading(true);
        progressTitle.textContent = 'Fetching authors from filtered papers…';
        progressBar.style.width = '50%';

        // Fetch authors for keyword-filtered papers (NEW)
        await showAuthorSelection(input, selectedKeywords);
    };
}

// ── Show author selection UI ───────────────────────
async function showAuthorSelection(input, selectedKeywords) {
    const source = document.getElementById('sourceSelect').value;

    try {
        // Fetch authors filtered by keywords
        const authorRes = await fetch('/api/get_authors', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                input,
                source,
                selected_keywords: selectedKeywords,
            }),
        });

        if (!authorRes.ok) {
            const err = await authorRes.json();
            throw new Error(err.error || 'Failed to fetch authors');
        }

        const authorData = await authorRes.json();

        // Display author selection panel
        const authorsSection = document.getElementById('authorsSection');
        const authorsList = document.getElementById('authorsList');
        const totalFilteredPapersCount = document.getElementById('totalFilteredPapersCount');

        totalFilteredPapersCount.textContent = authorData.total_papers;

        // Populate authors list
        authorsList.innerHTML = '';

        if (authorData.authors.length === 0) {
            authorsList.innerHTML = '<p style="color: var(--text-muted);">No authors found in filtered papers.</p>';
        } else {
            authorData.authors.forEach(({author, count}) => {
                const item = document.createElement('label');
                item.className = 'author-item';
                item.innerHTML = `
                    <input type="checkbox" value="${esc(author)}">
                    <span>${esc(author)}<span class="author-count">(${count})</span></span>
                `;
                authorsList.appendChild(item);
            });
        }

        authorsSection.hidden = false;

        // Handle Select All Authors
        document.getElementById('selectAllAuthorsBtn').onclick = () => {
            authorsList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
            });
        };

        // Handle Select None Authors
        document.getElementById('selectNoneAuthorsBtn').onclick = () => {
            authorsList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                cb.checked = false;
            });
        };

        // Handle Back to Keywords
        document.getElementById('backToKeywordsBtn').onclick = () => {
            authorsSection.hidden = true;
            showKeywordSelection(input, {keywords: selectedKeywords.map(k => ({keyword: k, count: 0}))});
        };

        // Handle Process Selected Authors
        document.getElementById('processByAuthorsBtn').onclick = async () => {
            const selectedAuthors = Array.from(
                authorsList.querySelectorAll('input[type="checkbox"]:checked')
            ).map(cb => cb.value);

            // Allow empty author selection (process all keyword-filtered papers)
            // (no validation error needed)

            // Hide author panel, show progress
            authorsSection.hidden = true;
            progressSec.hidden = false;
            setLoading(true);

            await startSearch(input, selectedKeywords, selectedAuthors);
        };

        setLoading(false);
        progressSec.hidden = true;

    } catch (err) {
        showError(err.message);
        setLoading(false);
    }
}

// ── Start search with selected keywords ─────────────────────
async function startSearch(input, selectedKeywords, selectedAuthors = []) {
    resultsSec.hidden = true;
    try {
        // Start job with selected keywords and authors
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                input,
                keep_sources: document.getElementById('keepSources').checked,
                source: document.getElementById('sourceSelect').value,
                selected_keywords: selectedKeywords,
                selected_authors: selectedAuthors,  // NEW
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

        // Listen for individual paper events (incremental rendering)
        evtSrc.addEventListener('paper', (e) => {
            const citationData = JSON.parse(e.data);
            renderCiteCard(citationData);
        });

        evtSrc.addEventListener('done', (e) => {
            evtSrc.close();
            const data = JSON.parse(e.data);
            progressTitle.textContent = 'Done!';
            progressBar.style.width = '100%';

            // Show summary
            if (data.message) {
                summaryStrip.textContent = data.message;
                summaryStrip.hidden = false;
            }

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
}

function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.hidden = false;
}
