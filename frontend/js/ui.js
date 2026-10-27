// Shared building blocks: dialogs, forms, tables, toasts and formatting.
const UI = (() => {
    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]))

    const PATTERN_DAYS = { MWF: ["Mon", "Wed", "Fri"], TTH: ["Tue", "Thu"] }

    // Simple line icons (24x24), keyed by page id; also used on dashboard cards.
    const ICON_PATHS = {
        dashboard: "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z",
        students: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20c0-3.3 3.6-6 8-6s8 2.7 8 6",
        profile: "M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM6.5 18.5c1.2-2 3.2-3 5.5-3s4.3 1 5.5 3M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
        instructors: "M3 9l9-4 9 4-9 4-9-4zM7 11v4c0 1.7 2.2 3 5 3s5-1.3 5-3v-4M21 9v5",
        teaching: "M4 5h7a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H4zM20 5h-7a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2h7z",
        courses: "M4 6l8-3 8 3-8 3-8-3zM4 11l8 3 8-3M4 16l8 3 8-3",
        subjects: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
        scheduling: "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5M8 14h3M13 14h3M8 17h3",
        classrooms: "M4 21V5l8-2 8 2v16M9 21v-5h6v5M8 8h2M14 8h2M8 12h2M14 12h2",
        enrollment: "M9 4h6v3H9zM7 5H5v16h14V5h-2M8 13l3 3 5-5",
        "my-enrollment": "M9 4h6v3H9zM7 5H5v16h14V5h-2M8 13l3 3 5-5",
        users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c0-3 2.9-5 6.5-5s6.5 2 6.5 5M16 4.5a3.5 3.5 0 0 1 0 6.5M18 15c2.2.6 3.5 2.4 3.5 5",
        settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
    }
    const icon = (id, cls = "icon") =>
        `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICON_PATHS[id] || ICON_PATHS.dashboard}"/></svg>`
    const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    // ---------- Formatting ----------

    function toMinutes(hhmm) {
        const [h, m] = hhmm.split(":").map(Number)
        return h * 60 + m
    }

    function fmtTime(hhmm) {
        if (!hhmm) return ""
        const [h, m] = hhmm.split(":").map(Number)
        return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`
    }

    const days = pattern => PATTERN_DAYS[pattern].join(", ")
    const timeRange = row => `${fmtTime(row.start_time)}–${fmtTime(row.end_time)}`
    const slotText = row => `${row.pattern} ${timeRange(row)}`

    function overlaps(a, b) {
        const shared = PATTERN_DAYS[a.pattern].some(d => PATTERN_DAYS[b.pattern].includes(d))
        return shared && toMinutes(a.start_time) < toMinutes(b.end_time)
            && toMinutes(b.start_time) < toMinutes(a.end_time)
    }

    function seats(row) {
        const cls = row.available_slots <= 0 ? "badge-danger" : row.available_slots <= 5 ? "badge-warn" : "badge-ok"
        const label = row.available_slots <= 0 ? "Full" : `${row.available_slots} open`
        return `<span class="badge ${cls}">${label}</span> <small class="muted">${row.enrolled_count}/${row.capacity}</small>`
    }

    const badge = (text, kind = "ok") => `<span class="badge badge-${kind}">${esc(text)}</span>`
    const button = (action, id, label, kind = "secondary") =>
        `<button type="button" class="btn btn-sm btn-${kind}" data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`
    const options = (list, value, label) => list.map(item => ({ value: item[value], label: label(item) }))

    // Course list built from rows that carry course_id/course_code, for roles
    // (instructors) that can't load the Courses module itself.
    const coursesFrom = rows => [...new Map(rows.map(r => [r.course_id, { id: r.course_id, code: r.course_code }])).values()]
        .sort((a, b) => a.code.localeCompare(b.code))

    // ---------- Feedback ----------

    function toast(message, type = "success") {
        const el = document.createElement("div")
        el.className = `toast toast-${type}`
        el.setAttribute("role", type === "error" ? "alert" : "status")
        el.textContent = message
        document.getElementById("toast-root").appendChild(el)
        setTimeout(() => el.remove(), type === "error" ? 8000 : 3500)
    }

    const loading = (text = "Loading…") => `<div class="state"><span class="spinner"></span> ${esc(text)}</div>`
    const empty = text => `<div class="state empty">${esc(text)}</div>`
    const errorState = text => `<div class="state error-state" role="alert">${esc(text)}</div>`

    // ---------- Dialogs ----------

    function openDialog({ title, body = "", wide = false, onClose }) {
        const backdrop = document.createElement("div")
        backdrop.className = "myModal"
        backdrop.innerHTML = `
            <div class="modal-content ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
                <button class="close-btn" type="button" aria-label="Close"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
                <h2>${esc(title)}</h2>
                <div class="dialog-body"></div>
            </div>`
        const bodyEl = backdrop.querySelector(".dialog-body")
        if (typeof body === "string") bodyEl.innerHTML = body
        else bodyEl.appendChild(body)

        const onKey = e => { if (e.key === "Escape") close() }
        function close() {
            backdrop.remove()
            document.removeEventListener("keydown", onKey)
            if (onClose) onClose()
        }
        backdrop.querySelector(".close-btn").addEventListener("click", close)
        backdrop.addEventListener("mousedown", e => { if (e.target === backdrop) close() })
        document.addEventListener("keydown", onKey)
        document.getElementById("dialog-root").appendChild(backdrop)
        return { el: backdrop, body: bodyEl, close }
    }

    function confirmAction(message, { confirmText = "Delete", danger = true } = {}) {
        return new Promise(resolve => {
            let answer = false
            const dialog = openDialog({
                title: "Please confirm",
                body: `<p>${esc(message)}</p>
                    <div class="dialog-actions">
                        <button type="button" class="btn btn-secondary" data-choice="no">Cancel</button>
                        <button type="button" class="btn ${danger ? "btn-danger" : "btn-primary"}" data-choice="yes">${esc(confirmText)}</button>
                    </div>`,
                onClose: () => resolve(answer),
            })
            dialog.body.addEventListener("click", e => {
                const choice = e.target.dataset.choice
                if (!choice) return
                answer = choice === "yes"
                dialog.close()
            })
            dialog.body.querySelector("[data-choice=no]").focus()
        })
    }

    // ---------- Forms ----------
    // Field spec: { name, label, type, required, options, section, help, full,
    //               min, max, step, minlength, maxlength, pattern, placeholder,
    //               numeric, display (shown but not submitted), disabled }

    function fieldHtml(f, value) {
        const attrs = ["min", "max", "step", "minlength", "maxlength", "pattern", "placeholder", "autocomplete"]
            .filter(a => f[a] !== undefined).map(a => `${a}="${esc(f[a])}"`).join(" ")
        const common = `name="${esc(f.name)}" ${f.required ? "required" : ""} ${f.display ? "readonly" : ""} ${f.disabled ? "disabled" : ""} ${attrs}`
        if (f.type === "checkbox") {
            return `<label class="check ${f.full ? "full" : ""}"><input type="checkbox" ${common} ${value ? "checked" : ""}> ${esc(f.label)}</label>`
        }
        if (f.type === "photo") {
            // Picker only; the page uploads the chosen file itself (see students.js).
            return `<div class="field full photo-field">
                <span>${esc(f.label)}</span>
                <div class="photo-picker">
                    <span class="avatar-img avatar-lg" data-photo-preview>${icon("students", "icon")}</span>
                    <div class="photo-actions">
                        <div class="photo-buttons">
                            <label class="btn btn-sm">Choose photo
                                <input type="file" name="${esc(f.name)}" accept="image/jpeg,image/png,image/webp" class="visually-hidden">
                            </label>
                            <button type="button" class="btn btn-sm btn-danger" data-photo-remove hidden>Remove</button>
                        </div>
                        <small class="muted">JPG, PNG or WebP, up to 2 MB.</small>
                    </div>
                </div>
            </div>`
        }
        let input
        if (f.type === "select") {
            const blank = f.blank === false ? "" : `<option value="">${esc(f.blank || "Select…")}</option>`
            input = `<select ${common}>${blank}${f.options.map(o =>
                `<option value="${esc(o.value)}" ${String(o.value) === String(value ?? "") ? "selected" : ""} ${o.disabled ? "disabled" : ""}>${esc(o.label)}</option>`
            ).join("")}</select>`
        } else if (f.type === "textarea") {
            input = `<textarea ${common} rows="3">${esc(value)}</textarea>`
        } else {
            input = `<input type="${f.type || "text"}" ${common} value="${esc(value)}">`
        }
        return `<label class="field ${f.full ? "full" : ""}">
            <span>${esc(f.label)}${f.required ? ' <b class="req" aria-hidden="true">*</b>' : ""}</span>
            ${input}
            ${f.help ? `<small class="muted">${esc(f.help)}</small>` : ""}
        </label>`
    }

    function formHtml(fields, values = {}) {
        let html = ""
        let section = null
        fields.forEach(f => {
            if (f.section !== section) {
                if (section !== null) html += "</div></fieldset>"
                section = f.section
                html += `<fieldset><legend>${esc(section || "Details")}</legend><div class="form-grid">`
            }
            html += fieldHtml(f, values[f.name])
        })
        return html + "</div></fieldset>"
    }

    function readForm(form, fields) {
        const data = {}
        fields.filter(f => !f.display && !f.disabled && f.type !== "photo").forEach(f => {
            const el = form.elements[f.name]
            if (f.type === "checkbox") data[f.name] = el.checked
            else if (f.type === "number" || f.numeric) data[f.name] = el.value === "" ? null : Number(el.value)
            else data[f.name] = el.value.trim()
        })
        return data
    }

    function formDialog({ title, fields, values = {}, submitText = "Save", wide = false, onSubmit, afterRender }) {
        const form = document.createElement("form")
        form.className = "form dialog-form"
        form.noValidate = false
        form.innerHTML = `${formHtml(fields, values)}
            <p class="form-error" role="alert" hidden></p>
            <div class="dialog-actions">
                <button type="button" class="btn btn-secondary" data-cancel>Cancel</button>
                <button type="submit" class="btn btn-primary">${esc(submitText)}</button>
            </div>`
        const dialog = openDialog({ title, body: form, wide })
        const errorEl = form.querySelector(".form-error")
        const submit = form.querySelector("[type=submit]")
        form.querySelector("[data-cancel]").addEventListener("click", dialog.close)
        if (afterRender) afterRender(form)
        const first = form.querySelector("input:not([readonly]):not([type=file]), select, textarea")
        if (first) first.focus()

        form.addEventListener("submit", async e => {
            e.preventDefault()
            errorEl.hidden = true
            submit.disabled = true
            submit.textContent = "Saving…"
            try {
                await onSubmit(readForm(form, fields), form)
                dialog.close()
            } catch (err) {
                errorEl.textContent = err.message
                errorEl.hidden = false
            } finally {
                submit.disabled = false
                submit.textContent = submitText
            }
        })
        return dialog
    }

    // ---------- Tables ----------
    // Column: { label, value: row => text } or { label, html: row => trusted html }

    // Tables longer than pageSize get a Previous/Next pager; every row stays in
    // the DOM (later pages are just hidden) so click handlers keep working.
    function table(columns, rows, actions, { pageSize = 10 } = {}) {
        const paged = rows.length > pageSize
        const head = columns.map(c => `<th scope="col" class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("") + (actions ? '<th scope="col"><span class="visually-hidden">Actions</span></th>' : "")
        const body = rows.map((row, i) => `<tr ${i >= pageSize ? "hidden" : ""}>${columns.map(c =>
            `<td data-label="${esc(c.label)}" class="${c.num ? "num" : ""}">${c.html ? c.html(row) : esc(c.value(row))}</td>`
        ).join("")}${actions ? `<td class="actions">${actions(row)}</td>` : ""}</tr>`).join("")
        const grid = `<div class="table-scroll"><table class="grid"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
        return paged
            ? `<div class="paged" data-page-size="${pageSize}">${grid}<div class="pager" data-local-pager>${pagerHtml(1, pageSize, rows.length, "data-local-page")}</div></div>`
            : grid
    }

    document.addEventListener("click", e => {
        const btn = e.target.closest("[data-local-page]")
        if (!btn) return
        const box = btn.closest(".paged")
        const size = Number(box.dataset.pageSize)
        const page = Number(btn.dataset.localPage)
        const rows = box.querySelectorAll(":scope > .table-scroll tbody > tr")
        rows.forEach((tr, i) => { tr.hidden = i < (page - 1) * size || i >= page * size })
        box.querySelector("[data-local-pager]").innerHTML = pagerHtml(page, size, rows.length, "data-local-page")
    })

    function pagerHtml(page, pageSize, total, attr = "data-page") {
        if (!total) return ""
        const pages = Math.max(1, Math.ceil(total / pageSize))
        const from = (page - 1) * pageSize + 1
        const to = Math.min(total, page * pageSize)
        return `<span>Showing ${from}–${to} of ${total}</span>
            <button type="button" class="btn btn-sm btn-secondary" ${attr}="${page - 1}" ${page <= 1 ? "disabled" : ""}>Previous</button>
            <span>Page ${page} of ${pages}</span>
            <button type="button" class="btn btn-sm btn-secondary" ${attr}="${page + 1}" ${page >= pages ? "disabled" : ""}>Next</button>`
    }

    // Client-side searchable, filterable, paginated list.
    function listView(container, { columns, rows = [], search, filters = [], pageSize = 10, actions,
                                   onAction, idKey = "id", emptyText = "No records yet." }) {
        const state = { rows, query: "", filterValues: filters.map(() => ""), page: 1 }
        container.innerHTML = `
            <div class="list-tools" ${search || filters.length ? "" : "hidden"}>
                ${search ? `<input type="search" class="search" placeholder="${esc(search.placeholder || "Search…")}" aria-label="Search">` : ""}
                ${filters.map((f, i) => `<select data-filter="${i}" aria-label="${esc(f.label)}">
                    <option value="">${esc(f.label)}</option>
                    ${f.options.map(o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("")}
                </select>`).join("")}
            </div>
            <div data-table></div>
            <div class="pager" data-pager></div>`
        const tableEl = container.querySelector("[data-table]")
        const pagerEl = container.querySelector("[data-pager]")

        function visibleRows() {
            const q = state.query.toLowerCase()
            return state.rows.filter(row =>
                (!q || search.text(row).toLowerCase().includes(q)) &&
                filters.every((f, i) => state.filterValues[i] === "" || f.match(row, state.filterValues[i]))
            )
        }

        function draw() {
            const list = visibleRows()
            const pages = Math.max(1, Math.ceil(list.length / pageSize))
            state.page = Math.min(state.page, pages)
            const pageRows = list.slice((state.page - 1) * pageSize, state.page * pageSize)
            tableEl.innerHTML = list.length
                ? table(columns, pageRows, actions, { pageSize: Infinity })
                : empty(state.rows.length ? "No records match your search or filters." : emptyText)
            pagerEl.innerHTML = pagerHtml(state.page, pageSize, list.length)
            loadPhotos(tableEl)
        }

        const searchEl = container.querySelector(".search")
        if (searchEl) searchEl.addEventListener("input", () => { state.query = searchEl.value.trim(); state.page = 1; draw() })
        container.querySelectorAll("[data-filter]").forEach(sel => sel.addEventListener("change", () => {
            state.filterValues[Number(sel.dataset.filter)] = sel.value
            state.page = 1
            draw()
        }))
        pagerEl.addEventListener("click", e => {
            const btn = e.target.closest("[data-page]")
            if (btn) { state.page = Number(btn.dataset.page); draw() }
        })
        tableEl.addEventListener("click", e => {
            const btn = e.target.closest("[data-action]")
            if (!btn || !onAction) return
            const row = state.rows.find(r => String(r[idKey]) === btn.dataset.id)
            onAction(btn.dataset.action, row, btn)
        })
        draw()
        return { setRows(newRows) { state.rows = newRows; draw() } }
    }

    // Weekly timetable: one row per time range, one column per weekday.
    function weekGrid(sections, label = s => `${s.subject_code} · ${s.section_code}`) {
        if (!sections.length) return empty("Nothing scheduled yet.")
        const ranges = [...new Map(sections.map(s => [`${s.start_time}-${s.end_time}`, s])).values()]
            .sort((a, b) => toMinutes(a.start_time) - toMinutes(b.start_time))
        const rows = ranges.map(r => {
            const cells = WEEKDAYS.map(day => {
                const here = sections.filter(s => s.start_time === r.start_time && s.end_time === r.end_time
                    && PATTERN_DAYS[s.pattern].includes(day))
                return `<td>${here.map(s => `<div class="chip">${esc(label(s))}<small>${esc(s.room_code || "No room")}</small></div>`).join("")}</td>`
            }).join("")
            return `<tr><th scope="row">${esc(timeRange(r))}</th>${cells}</tr>`
        }).join("")
        return `<div class="table-scroll"><table class="week"><thead><tr><th>Time</th>${WEEKDAYS.map(d => `<th>${d}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`
    }

    function tabs(container, items, onSelect) {
        container.innerHTML = `<div class="tabs" role="tablist">${items.map((t, i) =>
            `<button type="button" role="tab" class="tab" data-tab="${t.id}" aria-selected="${i === 0}">${esc(t.label)}</button>`
        ).join("")}</div><div data-tab-panel></div>`
        const panel = container.querySelector("[data-tab-panel]")
        const select = id => {
            container.querySelectorAll(".tab").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === id))
            onSelect(id, panel)
        }
        container.querySelector(".tabs").addEventListener("click", e => {
            const btn = e.target.closest("[data-tab]")
            if (btn) select(btn.dataset.tab)
        })
        select(items[0].id)
    }

    // Wraps an async action: shows a success toast or the server's error.
    async function run(action, successMessage) {
        try {
            const result = await action()
            UI.toast(successMessage || (result && result.message) || "Done.")
            return true
        } catch (err) {
            UI.toast(err.message, "error")
            return false
        }
    }

    // Round avatar: the student's photo when they have one, initials otherwise.
    // "Jasper Ayawan" -> "JA"; a single word gives its first two letters ("ayawan" -> "AY").
    function initials(name) {
        const words = String(name || "?").trim().split(/\s+/)
        return (words.length > 1 ? words[0][0] + words[1][0] : words[0].slice(0, 2)).toUpperCase()
    }

    function avatar(student, size = "sm") {
        const letters = initials(student.name)
        const photo = student.photo ? ` data-photo="/students/${student.id}/photo?v=${encodeURIComponent(student.photo)}"` : ""
        return `<span class="avatar-img avatar-${size}"${photo} aria-hidden="true">${esc(letters)}</span>`
    }

    function showPhoto(el, url) {
        el.style.backgroundImage = `url("${url}")`
        el.classList.add("has-photo")
    }

    async function loadPhotos(root) {
        root.querySelectorAll("[data-photo]:not(.has-photo)").forEach(async el => {
            const url = await apiImage(el.dataset.photo)
            if (url) showPhoto(el, url)
        })
    }

    function details(pairs) {
        return `<dl class="details">${pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v ?? "") || '<span class="muted">—</span>'}</dd>`).join("")}</dl>`
    }

    return {
        esc, icon, coursesFrom, fmtTime, days, timeRange, slotText, overlaps, seats, badge, button, options, toMinutes,
        toast, loading, empty, errorState, openDialog, confirmAction, formDialog, formHtml, readForm, table, pagerHtml,
        listView, weekGrid, tabs, run, details, initials, avatar, showPhoto, loadPhotos, PATTERN_DAYS,
    }
})()
