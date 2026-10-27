Pages.push({
    id: "scheduling",
    nav: "Class Scheduling",
    title: "Class Scheduling",
    visible: () => Auth.can("sections.view"),

    async render(el) {
        UI.tabs(el, [
            { id: "sections", label: "Class sections" },
            { id: "week", label: "Week view" },
            { id: "slots", label: "Time slots" },
        ], (tab, panel) => {
            panel.innerHTML = UI.loading()
            const views = { sections: renderSections, week: renderWeek, slots: renderTimeSlots }
            views[tab](panel).catch(err => { panel.innerHTML = UI.errorState(err.message) })
        })
    },
})

async function renderSections(panel) {
    const canManage = Auth.can("sections.manage")
    const [sections, courses, slots] = await Promise.all([
        api("/sections").then(r => r.data),
        api("/courses/").then(r => r.data),
        api("/time-slots").then(r => r.data),
    ])
    // Lists needed only for assigning instructors and rooms.
    const [subjects, instructors, rooms] = canManage ? await Promise.all([
        api("/subjects/").then(r => r.data),
        api("/instructors/").then(r => r.data),
        api("/classrooms/").then(r => r.data),
    ]) : [[], [], []]
    let allSections = sections

    panel.innerHTML = `<div class="page-actions">${canManage ? '<button type="button" class="btn btn-primary" data-add>Schedule a class</button>' : ""}</div><div data-list></div>`
    const canSeeRoster = row => Auth.can("enrollments.view") || (Auth.user.instructor_id && Auth.user.instructor_id === row.instructor_id)

    const list = UI.listView(panel.querySelector("[data-list]"), {
        rows: sections,
        search: { placeholder: "Search subject, instructor or room…",
                  text: r => `${r.subject_code} ${r.subject_title} ${r.instructor_name || ""} ${r.room_code || ""} ${r.section_code}` },
        filters: [
            { label: "All courses", options: UI.options(courses, "id", c => c.code), match: (r, v) => String(r.course_id) === v },
            { label: "MWF & TTH", options: [{ value: "MWF", label: "MWF" }, { value: "TTH", label: "TTH" }], match: (r, v) => r.pattern === v },
            { label: "Any availability", options: [{ value: "open", label: "Has open slots" }, { value: "full", label: "Full" }],
              match: (r, v) => (v === "open") === (r.available_slots > 0) },
        ],
        pageSize: 15,
        columns: [
            { label: "Subject", value: r => `${r.subject_code} — ${r.subject_title}` },
            { label: "Section", value: r => r.section_code },
            { label: "Days", value: r => UI.days(r.pattern) },
            { label: "Start", value: r => UI.fmtTime(r.start_time) },
            { label: "End", value: r => UI.fmtTime(r.end_time) },
            { label: "Instructor", html: r => r.instructor_name ? UI.esc(r.instructor_name) : UI.badge("Unassigned", "warn") },
            { label: "Room", html: r => r.room_code ? UI.esc(r.room_code) : UI.badge("Unassigned", "warn") },
            { label: "Slots", html: r => UI.seats(r) },
        ],
        actions: r => (canSeeRoster(r) ? UI.button("roster", r.id, "Roster") : "") +
            (canManage ? UI.button("edit", r.id, "Edit / reassign", "edit") + UI.button("delete", r.id, "Delete", "danger") : ""),
        emptyText: "No classes scheduled yet.",
        onAction: async (action, row) => {
            if (action === "roster") showRoster(row.id)
            if (action === "edit") openForm(row)
            if (action === "delete") {
                const ok = await UI.confirmAction(`Delete ${row.subject_code} section ${row.section_code}?`)
                if (ok && await UI.run(() => api(`/sections/${row.id}`, { method: "DELETE" }))) reload()
            }
        },
    })

    async function reload() {
        allSections = (await api("/sections")).data
        list.setRows(allSections)
    }

    // Grey out instructors and rooms that are inactive or already busy in the chosen slot.
    function markAvailability(form, current) {
        const slot = slots.find(s => String(s.id) === form.elements.time_slot_id.value)
        const busy = (key, id) => slot && allSections.find(s =>
            s[key] === id && (!current || s.id !== current.id) && UI.overlaps(slot, s))
        const relabel = (select, list, key, label, isActive) => {
            Array.from(select.options).forEach(opt => {
                if (!opt.value) return
                const item = list.find(i => String(i.id) === opt.value)
                const clash = busy(key, item.id)
                opt.disabled = !isActive(item) || Boolean(clash)
                opt.textContent = label(item) + (!isActive(item) ? " — unavailable" : clash ? ` — busy (${clash.subject_code} ${clash.section_code})` : "")
            })
        }
        relabel(form.elements.instructor_id, instructors, "instructor_id", i => i.name, i => i.is_active)
        relabel(form.elements.classroom_id, rooms, "classroom_id", r => `${r.room_code} (${r.capacity} seats)`, r => r.is_active)
    }

    const openForm = section => UI.formDialog({
        title: section ? `Edit ${section.subject_code} section ${section.section_code}` : "Schedule a Class",
        wide: true,
        fields: [
            { name: "subject_id", label: "Subject", type: "select", required: true, numeric: true, full: true,
              options: UI.options(subjects, "id", s => `${s.code} — ${s.title} (${s.course_code}, ${s.units} units)`) },
            { name: "section_code", label: "Section code", required: true, maxlength: 10, placeholder: "e.g. A" },
            { name: "time_slot_id", label: "Days and time", type: "select", required: true, numeric: true,
              options: UI.options(slots, "id", s => `${UI.slotText(s)}${s.is_exception ? " (approved exception)" : ""}`) },
            { name: "instructor_id", label: "Instructor", type: "select", numeric: true, blank: "Unassigned",
              options: UI.options(instructors, "id", i => i.name) },
            { name: "classroom_id", label: "Classroom", type: "select", numeric: true, blank: "Unassigned",
              options: UI.options(rooms, "id", r => r.room_code) },
            { name: "capacity", label: "Capacity", type: "number", required: true, min: 1, max: 30,
              help: "Maximum 30 students per class section." },
        ],
        values: section || { capacity: 30 },
        submitText: section ? "Save Changes" : "Schedule",
        afterRender(form) {
            markAvailability(form, section)
            form.elements.time_slot_id.addEventListener("change", () => markAvailability(form, section))
        },
        async onSubmit(body) {
            const res = section
                ? await api(`/sections/${section.id}`, { method: "PUT", body })
                : await api("/sections", { method: "POST", body })
            UI.toast(res.message)
            reload()
        },
    })

    panel.querySelector("[data-add]")?.addEventListener("click", () => openForm(null))
}

async function renderWeek(panel) {
    const [sections, courses] = await Promise.all([api("/sections").then(r => r.data), api("/courses/").then(r => r.data)])
    panel.innerHTML = `<div class="list-tools">
            <select data-course aria-label="Course"><option value="">All courses</option>
                ${courses.map(c => `<option value="${c.id}">${UI.esc(c.code)}</option>`).join("")}</select>
        </div><div data-grid></div>`
    const draw = () => {
        const course = panel.querySelector("[data-course]").value
        const shown = sections.filter(s => !course || String(s.course_id) === course)
        panel.querySelector("[data-grid]").innerHTML = UI.weekGrid(shown,
            s => `${s.subject_code} ${s.section_code} · ${s.available_slots} open`)
    }
    panel.querySelector("[data-course]").addEventListener("change", draw)
    draw()
}

async function renderTimeSlots(panel) {
    const canManage = Auth.can("sections.manage")
    const settings = Auth.can("settings.view") ? (await api("/settings")).data : null
    panel.innerHTML = `
        ${settings ? `<p class="muted">Rooms operate ${UI.fmtTime(settings.room_open_time)}–${UI.fmtTime(settings.room_close_time)}.
            MWF classes last ${settings.mwf_duration_minutes} minutes and TTH classes ${settings.tth_duration_minutes} minutes,
            unless a slot is marked as an approved exception.</p>` : ""}
        <div class="page-actions">${canManage ? '<button type="button" class="btn btn-primary" data-add>Add time slot</button>' : ""}</div>
        <div data-list></div>`

    const list = UI.listView(panel.querySelector("[data-list]"), {
        columns: [
            { label: "Pattern", value: r => r.pattern },
            { label: "Days", value: r => UI.days(r.pattern) },
            { label: "Start", value: r => UI.fmtTime(r.start_time) },
            { label: "End", value: r => UI.fmtTime(r.end_time) },
            { label: "Minutes", value: r => UI.toMinutes(r.end_time) - UI.toMinutes(r.start_time) },
            { label: "Type", html: r => r.is_exception ? UI.badge("Approved exception", "warn") : UI.badge("Standard") },
            { label: "Classes using it", value: r => r.section_count },
            { label: "Note", value: r => r.note },
        ],
        actions: canManage ? r => UI.button("delete", r.id, "Delete", "danger") : null,
        emptyText: "No time slots configured.",
        onAction: async (action, row) => {
            const ok = await UI.confirmAction(`Delete the ${UI.slotText(row)} time slot?`)
            if (ok && await UI.run(() => api(`/time-slots/${row.id}`, { method: "DELETE" }))) load()
        },
    })

    async function load() {
        list.setRows((await api("/time-slots")).data)
    }

    panel.querySelector("[data-add]")?.addEventListener("click", () => UI.formDialog({
        title: "Add Time Slot",
        fields: [
            { name: "pattern", label: "Days", type: "select", required: true,
              options: [{ value: "MWF", label: "MWF (Mon, Wed, Fri)" }, { value: "TTH", label: "TTH (Tue, Thu)" }] },
            { name: "start_time", label: "Start time", type: "time", required: true },
            { name: "end_time", label: "End time", type: "time", required: true },
            { name: "note", label: "Note", maxlength: 200 },
            { name: "is_exception", label: "Approved exception to the standard class length", type: "checkbox", full: true },
        ],
        async onSubmit(body) {
            UI.toast((await api("/time-slots", { method: "POST", body })).message)
            load()
        },
    }))
    await load()
}
