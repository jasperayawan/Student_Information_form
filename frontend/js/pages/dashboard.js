Pages.push({
    id: "dashboard",
    nav: "Dashboard",
    title: "Dashboard",
    visible: () => Auth.can("dashboard.view"),

    async render(el) {
        const { data } = await api("/dashboard")
        el.innerHTML = `${greeting()}<div data-dash></div>`
        const dash = el.querySelector("[data-dash]")

        if (data.stats) await renderAdminDashboard(dash, data)
        else if (data.role === "instructor") renderInstructorDashboard(dash, data.teaching)
        else if (data.role === "student") renderStudentDashboard(dash, data.studies)
    },
})

const DASH_PAGE_SIZE = 5

function greeting() {
    const hour = new Date().getHours()
    const part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"
    const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })
    return `<div class="dash-greeting">
        <p class="eyebrow">${UI.esc(today)}</p>
        <p class="greeting-line">${part}, <strong>${UI.esc(Auth.user.username)}</strong></p>
    </div>`
}

// label · value · optional supporting line · icon (stat-tile contract)
function statTile({ label, value, note, icon, page }) {
    const inner = `<span class="stat-icon">${UI.icon(icon)}</span>
        <span class="stat-body">
            <span class="stat-label">${UI.esc(label)}</span>
            <span class="stat-value">${UI.esc(value)}</span>
            ${note ? `<span class="stat-note">${UI.esc(note)}</span>` : ""}
        </span>`
    return page && Pages.some(p => p.id === page && p.visible())
        ? `<a class="stat-tile" href="#/${page}">${inner}</a>`
        : `<div class="stat-tile">${inner}</div>`
}

function meter(fraction, label) {
    const pct = Math.round(Math.min(1, Math.max(0, fraction)) * 100)
    const level = pct >= 90 ? "danger" : pct >= 75 ? "warn" : "ok"
    return `<div class="meter meter-${level}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="${UI.esc(label)}">
        <span style="width:${pct}%"></span></div>`
}

const weeklyHours = s => (UI.toMinutes(s.end_time) - UI.toMinutes(s.start_time)) * UI.PATTERN_DAYS[s.pattern].length / 60
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : word.endsWith("s") ? "es" : "s"}`

async function renderAdminDashboard(el, data) {
    const s = data.stats
    const c = data.compliance
    const [courses, sections, instructors, rooms] = await Promise.all([
        api("/courses/").then(r => r.data),
        api("/sections").then(r => r.data),
        Auth.can("instructors.view") ? api("/instructors/").then(r => r.data) : [],
        api("/reports/room-utilization").then(r => r.data),
    ])
    const filled = s.total_seats - s.available_slots
    const coursesOk = c.courses.filter(x => x.meets_minimum).length

    el.innerHTML = `
        <div class="dash-top">
            <section class="hero-card" aria-labelledby="hero-label">
                <span class="stat-label" id="hero-label">Available class slots</span>
                <span class="hero-value">${s.available_slots.toLocaleString()}</span>
                <span class="stat-note">of ${s.total_seats.toLocaleString()} seats across ${plural(s.sections, "scheduled class")}</span>
                ${meter(s.total_seats ? filled / s.total_seats : 0, "Seats filled")}
                <span class="meter-caption"><span>${filled.toLocaleString()} filled</span><span>${s.total_seats ? Math.round(100 * filled / s.total_seats) : 0}%</span></span>
            </section>
            <div class="stat-grid">
                ${statTile({ label: "Registered students", value: s.students, note: `${s.enrolled_students} enrolled in a class`, icon: "students", page: "students" })}
                ${statTile({ label: "Instructors", value: s.instructors, note: `${s.teaching_instructors} teaching · ${s.active_instructors} active`, icon: "instructors", page: "instructors" })}
                ${statTile({ label: "Courses", value: s.courses, note: `${coursesOk} of ${s.courses} meet the subject minimum`, icon: "courses", page: "courses" })}
                ${statTile({ label: "Subjects", value: s.subjects, note: `${s.scheduled_subjects} have scheduled classes`, icon: "subjects", page: "subjects" })}
                ${statTile({ label: "Scheduled classes", value: s.sections, note: `${plural(s.time_slots, "time slot")} configured`, icon: "scheduling", page: "scheduling" })}
                ${statTile({ label: "Classrooms in use", value: s.rooms_in_use, note: `of ${s.active_classrooms} available rooms`, icon: "classrooms", page: "classrooms" })}
            </div>
        </div>

        <div class="dash-row">
            <section class="panel">
                <div class="panel-head"><h2>Students by course</h2><span class="muted">${plural(s.students, "student")}</span></div>
                ${courseChart(courses)}
            </section>
            <section class="panel">
                <div class="panel-head"><h2>Requirement checks</h2></div>
                ${checklist(c)}
            </section>
        </div>

        <div class="dash-row">
            ${instructors.length ? `<section class="panel">
                <div class="panel-head"><h2>Instructor workload</h2><span class="muted">${plural(instructors.length, "instructor")}</span></div>
                <div data-instructors></div>
            </section>` : ""}
            <section class="panel">
                <div class="panel-head"><h2>Room utilization</h2><span class="muted">${s.rooms_in_use} of ${rooms.length} in use</span></div>
                <div data-rooms></div>
            </section>
        </div>

        ${c.subjects_below_offering_minimum.length ? `<section class="panel">
            <div class="panel-head"><h2>Subjects below the offering target</h2>
                <span class="muted">target: ${c.min_offerings_per_day} sections on each day a subject meets</span></div>
            <div data-subjects></div>
        </section>` : ""}`

    bindChartTooltip(el)

    if (instructors.length) {
        const rows = instructors.map(i => {
            const mine = sections.filter(x => x.instructor_id === i.id)
            return { ...i, classes: mine.length, students: mine.reduce((n, x) => n + x.enrolled_count, 0),
                     hours: mine.reduce((n, x) => n + weeklyHours(x), 0) }
        }).sort((a, b) => b.classes - a.classes || a.name.localeCompare(b.name))
        UI.listView(el.querySelector("[data-instructors]"), {
            rows,
            pageSize: DASH_PAGE_SIZE,
            search: { placeholder: "Search instructors…", text: r => `${r.name} ${r.department}` },
            columns: [
                { label: "Instructor", html: r => `<span class="person"><strong>${UI.esc(r.name)}</strong><small class="muted">${UI.esc(r.department)}</small></span>` },
                { label: "Classes", value: r => r.classes, num: true },
                { label: "Students", value: r => r.students, num: true },
                { label: "Hours / week", value: r => r.hours.toFixed(1), num: true },
                { label: "Status", html: r => r.is_active ? UI.badge("Active") : UI.badge("Inactive", "muted") },
            ],
            emptyText: "No instructors registered yet.",
        })
    }

    UI.listView(el.querySelector("[data-rooms]"), {
        rows: [...rooms].sort((a, b) => b.utilization_percent - a.utilization_percent || a.room_code.localeCompare(b.room_code)),
        pageSize: DASH_PAGE_SIZE,
        search: { placeholder: "Search rooms…", text: r => r.room_code },
        filters: [{ label: "All rooms", options: [{ value: "used", label: "In use" }, { value: "free", label: "No classes" }],
                    match: (r, v) => (v === "used") === (r.sections > 0) }],
        idKey: "room_code",
        columns: [
            { label: "Room", value: r => r.room_code },
            { label: "Classes", value: r => r.sections, num: true },
            { label: "Booked", value: r => `${r.booked_hours} / ${r.open_hours} h`, num: true },
            { label: "Utilization", html: r => `<div class="util">${meter(r.utilization_percent / 100, `${r.room_code} utilization`)}<span>${r.utilization_percent}%</span></div>` },
        ],
    })

    if (c.subjects_below_offering_minimum.length) {
        UI.listView(el.querySelector("[data-subjects]"), {
            rows: c.subjects_below_offering_minimum,
            pageSize: DASH_PAGE_SIZE,
            search: { placeholder: "Search subjects…", text: r => `${r.code} ${r.title}` },
            columns: [
                { label: "Code", value: r => r.code },
                { label: "Descriptive title", value: r => r.title },
                { label: "Course", value: r => r.course_code },
                { label: "Sections per day", html: r => {
                    const days = Object.entries(r.offerings_per_day).filter(([, n]) => n > 0)
                    return days.length
                        ? days.map(([d, n]) => `<span class="day-pill">${d} ${n}</span>`).join(" ")
                        : UI.badge("Not scheduled", "muted")
                } },
            ],
        })
    }
}

// Single-series horizontal bars: one hue, value at the tip, hover/focus tooltip.
function courseChart(courses) {
    if (!courses.length) return UI.empty("No courses yet.")
    const max = Math.max(1, ...courses.map(c => c.student_count))
    return `<div class="bar-chart" role="list">${courses.map(c => {
        const pct = (c.student_count / max) * 100
        const tip = `${c.code}: ${plural(c.student_count, "student")} · ${plural(c.subject_count, "subject")}`
        return `<div class="bar-row" role="listitem" tabindex="0" data-tip="${UI.esc(tip)}" aria-label="${UI.esc(tip)}">
            <span class="bar-label" title="${UI.esc(c.name)}">${UI.esc(c.code)}</span>
            <span class="bar-track"><span class="bar-fill" style="width:calc((100% - 40px) * ${pct / 100})"></span><span class="bar-value">${c.student_count}</span></span>
        </div>`
    }).join("")}</div><div class="chart-tip" role="tooltip" hidden></div>`
}

function bindChartTooltip(root) {
    const tip = root.querySelector(".chart-tip")
    const chart = root.querySelector(".bar-chart")
    if (!tip || !chart) return
    const show = row => {
        tip.textContent = row.dataset.tip
        tip.hidden = false
        const box = row.getBoundingClientRect()
        const host = chart.parentElement.getBoundingClientRect()
        tip.style.left = `${box.left - host.left + 56}px`
        tip.style.top = `${box.top - host.top - 34}px`
    }
    const hide = () => { tip.hidden = true }
    chart.addEventListener("mouseover", e => { const row = e.target.closest(".bar-row"); if (row) show(row) })
    chart.addEventListener("mouseleave", hide)
    chart.addEventListener("focusin", e => { const row = e.target.closest(".bar-row"); if (row) show(row) })
    chart.addEventListener("focusout", hide)
}

function checklist(c) {
    const short = c.subjects_below_offering_minimum.length
    const totalSubjects = c.courses.reduce((n, x) => n + x.subject_count, 0)
    const items = [
        { ok: c.course_count_ok, text: `${c.courses.length} of ${c.required_course_count} courses offered` },
        ...c.courses.map(x => ({
            ok: x.meets_minimum,
            text: `${x.code}: ${x.subject_count} of ${c.min_subjects_per_course} required subjects`,
        })),
        { ok: short === 0, text: totalSubjects
            ? `${totalSubjects - short} of ${totalSubjects} subjects offered ${c.min_offerings_per_day}× per day`
            : "No subjects to check yet" },
    ]
    return `<ul class="checklist">${items.map(i => `<li class="${i.ok ? "is-ok" : "is-warn"}">
        <span class="check-icon" aria-hidden="true">${i.ok ? "✓" : "!"}</span>
        <span>${UI.esc(i.text)}</span>
        <span class="visually-hidden">${i.ok ? "met" : "needs attention"}</span>
    </li>`).join("")}</ul>`
}

function renderInstructorDashboard(el, teaching) {
    if (!teaching) {
        el.innerHTML = UI.empty("Your account is not linked to an instructor record yet. Please contact an administrator.")
        return
    }
    const sections = teaching.sections
    const hours = sections.reduce((n, s) => n + weeklyHours(s), 0)
    el.innerHTML = `
        <div class="stat-grid stat-grid-3">
            ${statTile({ label: "Classes I teach", value: sections.length, icon: "teaching", page: "teaching" })}
            ${statTile({ label: "Students in my classes", value: teaching.students, icon: "students" })}
            ${statTile({ label: "Teaching hours / week", value: hours.toFixed(1), icon: "scheduling" })}
        </div>
        <section class="panel"><div class="panel-head"><h2>My classes</h2></div><div data-classes></div></section>
        <section class="panel"><div class="panel-head"><h2>My teaching week</h2></div>${UI.weekGrid(sections)}</section>`
    UI.listView(el.querySelector("[data-classes]"), {
        rows: sections,
        pageSize: DASH_PAGE_SIZE,
        columns: [...SECTION_COLUMNS],
        actions: r => UI.button("roster", r.id, "Roster"),
        onAction: (action, row) => showRoster(row.id),
        emptyText: "No classes assigned yet.",
    })
}

function renderStudentDashboard(el, studies) {
    if (!studies) {
        el.innerHTML = UI.empty("Your account is not linked to a student record yet. Please contact an administrator.")
        return
    }
    const classes = studies.classes
    el.innerHTML = `
        <div class="stat-grid stat-grid-3">
            ${statTile({ label: "Enrolled classes", value: classes.length, icon: "my-enrollment", page: "my-enrollment" })}
            ${statTile({ label: "Total units", value: studies.units, icon: "subjects" })}
            ${statTile({ label: "Hours / week", value: classes.reduce((n, s) => n + weeklyHours(s), 0).toFixed(1), icon: "scheduling" })}
        </div>
        <section class="panel"><div class="panel-head"><h2>My classes</h2></div><div data-classes></div></section>
        <section class="panel"><div class="panel-head"><h2>My weekly schedule</h2></div>${UI.weekGrid(classes)}</section>`
    UI.listView(el.querySelector("[data-classes]"), {
        rows: classes,
        pageSize: DASH_PAGE_SIZE,
        columns: [
            { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
            { label: "Units", value: r => r.units, num: true },
            { label: "Schedule", value: r => UI.slotText(r) },
            { label: "Room", value: r => r.room_code || "TBA" },
            { label: "Instructor", value: r => r.instructor_name || "TBA" },
        ],
        emptyText: "You are not enrolled in any class yet.",
    })
}
