Pages.push({
    id: "classrooms",
    nav: "Classrooms",
    title: "Classroom Management",
    visible: () => Auth.can("classrooms.view"),

    async render(el) {
        UI.tabs(el, [
            { id: "rooms", label: "Rooms" },
            { id: "availability", label: "Room availability" },
        ], (tab, panel) => {
            panel.innerHTML = UI.loading()
            const view = tab === "rooms" ? renderRooms : renderAvailability
            view(panel).catch(err => { panel.innerHTML = UI.errorState(err.message) })
        })
    },
})

async function renderRooms(panel) {
    const canManage = Auth.can("classrooms.manage")
    panel.innerHTML = `<div class="page-actions">${canManage ? '<button type="button" class="btn btn-primary" data-add>Add room</button>' : ""}</div><div data-list></div>`

    const list = UI.listView(panel.querySelector("[data-list]"), {
        search: { placeholder: "Search rooms…", text: r => `${r.room_code} ${r.name}` },
        filters: [{ label: "Any status", options: [{ value: "1", label: "Available" }, { value: "0", label: "Unavailable" }],
                    match: (r, v) => String(r.is_active) === v }],
        pageSize: 15,
        columns: [
            { label: "Room ID", value: r => r.room_code },
            { label: "Name", value: r => r.name },
            { label: "Seats", value: r => r.capacity, num: true },
            { label: "Classes", value: r => r.section_count, num: true },
            { label: "Status", html: r => r.is_active ? UI.badge("Available") : UI.badge("Unavailable", "muted") },
        ],
        actions: r => UI.button("view", r.id, "Schedule") +
            (canManage ? UI.button("edit", r.id, "Edit", "edit") + UI.button("delete", r.id, "Delete", "danger") : ""),
        emptyText: "No rooms registered.",
        onAction: async (action, row) => {
            if (action === "view") {
                const dialog = UI.openDialog({ title: `Room ${row.room_code}`, body: UI.loading(), wide: true })
                try {
                    const { data } = await api(`/classrooms/${row.id}`)
                    dialog.body.innerHTML = data.sections.length
                        ? UI.table(SECTION_COLUMNS.filter(c => c.label !== "Room").concat(
                            [{ label: "Instructor", value: r => r.instructor_name || "TBA" }]), data.sections) + UI.weekGrid(data.sections)
                        : UI.empty("No classes are assigned to this room.")
                } catch (err) {
                    dialog.body.innerHTML = UI.errorState(err.message)
                }
            }
            if (action === "edit") openForm(row)
            if (action === "delete") {
                const ok = await UI.confirmAction(`Delete room ${row.room_code}?`)
                if (ok && await UI.run(() => api(`/classrooms/${row.id}`, { method: "DELETE" }))) load()
            }
        },
    })

    const openForm = room => UI.formDialog({
        title: room ? `Edit ${room.room_code}` : "Add Room",
        fields: [
            { name: "room_code", label: "Room ID", required: true, maxlength: 20 },
            { name: "name", label: "Name / location", maxlength: 100 },
            { name: "capacity", label: "Seats", type: "number", required: true, min: 1, max: 500 },
            { name: "is_active", label: "Available for scheduling", type: "checkbox", full: true },
        ],
        values: room || { capacity: 30, is_active: true },
        async onSubmit(body) {
            const res = room
                ? await api(`/classrooms/${room.id}`, { method: "PUT", body })
                : await api("/classrooms/", { method: "POST", body })
            UI.toast(res.message)
            load()
        },
    })

    async function load() {
        list.setRows((await api("/classrooms/")).data)
    }
    panel.querySelector("[data-add]")?.addEventListener("click", () => openForm(null))
    await load()
}

async function renderAvailability(panel) {
    panel.innerHTML = `<div class="list-tools">
            <select data-pattern aria-label="Days"><option value="MWF">MWF (Mon, Wed, Fri)</option><option value="TTH">TTH (Tue, Thu)</option></select>
            <label class="check"><input type="checkbox" data-free-only> Only rooms with a free slot</label>
        </div><div data-grid>${UI.loading()}</div>`
    const grid = panel.querySelector("[data-grid]")

    async function draw() {
        grid.innerHTML = UI.loading()
        try {
            const { data } = await api("/classrooms/availability", { query: { pattern: panel.querySelector("[data-pattern]").value } })
            const freeOnly = panel.querySelector("[data-free-only]").checked
            const rooms = data.rooms.filter(r => !freeOnly || r.cells.some(c => c.free))
            if (!data.time_slots.length) {
                grid.innerHTML = UI.empty("No time slots are configured for these days. Add them under Class Scheduling → Time slots.")
                return
            }
            grid.innerHTML = `<p class="muted">Operating hours: ${UI.fmtTime(data.settings.room_open_time)}–${UI.fmtTime(data.settings.room_close_time)}.
                <span class="badge badge-ok">Free</span> rooms can be assigned to a class in that slot.</p>
                <div class="table-scroll"><table class="availability">
                <thead><tr><th>Room</th>${data.time_slots.map(s => `<th>${UI.esc(UI.timeRange(s))}</th>`).join("")}</tr></thead>
                <tbody>${rooms.map(r => `<tr><th scope="row">${UI.esc(r.room_code)}</th>${r.cells.map(c =>
                    c.section ? `<td class="busy">${UI.esc(c.section.subject_code)} ${UI.esc(c.section.section_code)}</td>`
                        : c.free ? '<td class="free">Free</td>' : '<td class="off">Unavailable</td>'
                ).join("")}</tr>`).join("")}</tbody></table></div>`
        } catch (err) {
            grid.innerHTML = UI.errorState(err.message)
        }
    }
    panel.querySelector("[data-pattern]").addEventListener("change", draw)
    panel.querySelector("[data-free-only]").addEventListener("change", draw)
    await draw()
}
