// Talks to the FastAPI backend. When the page is served by the backend
// itself (http://127.0.0.1:8000/app/) the same origin is used; otherwise
// (Live Server, file://) the default local API address.
const API = location.protocol.startsWith("http") && location.pathname.startsWith("/app/")
    ? location.origin
    : "http://127.0.0.1:8000"

// Each page script registers itself here; index.js builds the navigation.
const Pages = []

const Auth = {
    token: readStorage("srs_token"),
    user: null,
    can(permission) {
        return Boolean(this.user && this.user.permissions.includes(permission))
    },
    save(token) {
        this.token = token
        writeStorage("srs_token", token)
    },
    clear() {
        this.token = null
        this.user = null
        writeStorage("srs_token", null)
    },
}

function readStorage(key) {
    try { return localStorage.getItem(key) } catch { return null }
}

function writeStorage(key, value) {
    try {
        if (value === null) localStorage.removeItem(key)
        else localStorage.setItem(key, value)
    } catch { /* storage blocked: the session just won't survive a reload */ }
}

const FRIENDLY_FORMATS = {
    contact_number: "must be 7 to 15 digits (an optional leading + is allowed)",
    email: "must be a valid email address",
    start_time: "must be a time like 19:30",
    end_time: "must be a time like 20:30",
    username: "may only contain letters, numbers and . _ @ -",
}

function fieldName(loc = []) {
    const name = String(loc[loc.length - 1] ?? "value")
    return name.replace(/_id$/, "").replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase())
}

function errorMessage(data, status) {
    const detail = data && data.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
        return detail.map(err => {
            const key = err.loc && err.loc[err.loc.length - 1]
            if (err.type === "string_pattern_mismatch" && FRIENDLY_FORMATS[key]) {
                return `${fieldName(err.loc)} ${FRIENDLY_FORMATS[key]}.`
            }
            if (err.type === "extra_forbidden") return `${fieldName(err.loc)} cannot be changed here.`
            return `${fieldName(err.loc)}: ${String(err.msg).replace(/^Value error, /, "")}`
        }).join(" ")
    }
    return `Request failed (${status}).`
}

async function api(path, { method = "GET", body, query } = {}) {
    let url = API + path
    if (query) {
        const params = new URLSearchParams()
        Object.entries(query).forEach(([key, value]) => {
            if (value !== "" && value !== null && value !== undefined) params.set(key, value)
        })
        if (params.toString()) url += "?" + params
    }
    const headers = {}
    if (body !== undefined) headers["Content-Type"] = "application/json"
    return send(path, url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
    })
}

// Uploads one file as multipart/form-data (the browser sets the boundary).
function apiUpload(path, file, { field = "photo", method = "PUT" } = {}) {
    const form = new FormData()
    form.append(field, file)
    return send(path, API + path, { method, headers: {}, body: form })
}

async function send(path, url, init) {
    if (Auth.token) init.headers.Authorization = `Bearer ${Auth.token}`
    let response
    try {
        response = await fetch(url, init)
    } catch {
        throw new Error("Cannot reach the server. Make sure the backend is running on port 8000.")
    }
    const data = await response.json().catch(() => ({}))
    if (response.status === 401 && Auth.token && path !== "/auth/login") {
        Auth.clear()
        window.dispatchEvent(new Event("auth:expired"))
    }
    if (!response.ok) throw new Error(errorMessage(data, response.status))
    return data
}

// Protected images can't use a plain <img src> (it can't send the sign-in
// token), so they are fetched and shown through a local object URL.
const imageCache = new Map()

function apiImage(path) {
    if (!imageCache.has(path)) {
        imageCache.set(path, fetch(API + path, { headers: Auth.token ? { Authorization: `Bearer ${Auth.token}` } : {} })
            .then(res => (res.ok ? res.blob() : null))
            .then(blob => (blob ? URL.createObjectURL(blob) : null))
            .catch(() => null))
    }
    return imageCache.get(path)
}
