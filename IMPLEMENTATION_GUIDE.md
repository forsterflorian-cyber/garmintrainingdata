# Implementierungs-Guide: Priorität 1 & 2 Fixes

## Priorität 1 (Sofort umsetzen)

### Fix 1: JWT-Validierung korrigieren
**Datei:** `auth_supabase.py`

**Aktuelles Problem:**
```python
options={
    "verify_exp": True,
    "verify_aud": False,  # ⚠️ Deaktiviert
    "verify_iss": False,  # ⚠️ Deaktiviert
    "require": ["exp", "sub"],
}
```

**Lösung:**
```python
def _verify_token(token: str) -> dict:
    """Verify JWT token with validation."""
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")

        if algorithm not in SUPPORTED_JWT_ALGORITHMS:
            raise jwt.InvalidTokenError(f"unsupported token algorithm: {algorithm}")

        if algorithm == "HS256":
            if not SUPABASE_JWT_SECRET:
                raise RuntimeError("SUPABASE_JWT_SECRET is required for HS256 token verification.")
            key = SUPABASE_JWT_SECRET
        else:
            jwks_client = _get_jwks_client()
            key = jwks_client.get_signing_key_from_jwt(token).key

        # NEU: Supabase spezifische Konfiguration
        SUPABASE_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "")
        expected_audience = "authenticated"
        expected_issuer = f"https://{SUPABASE_PROJECT_REF}.supabase.co/auth/v1" if SUPABASE_PROJECT_REF else None

        payload = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            options={
                "verify_exp": True,
                "verify_aud": True,  # NEU: Aktiviert
                "verify_iss": bool(expected_issuer),  # NEU: Aktiviert wenn Projekt-Ref vorhanden
                "require": ["exp", "sub", "aud", "iss"],
            },
            audience=expected_audience,
            issuer=expected_issuer,
        )

        if not payload.get("sub"):
            raise jwt.InvalidTokenError("missing token subject")

        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, timezone.utc) < datetime.now(timezone.utc):
            raise jwt.InvalidTokenError("token expired")

        return payload

    except jwt.ExpiredSignatureError:
        raise jwt.InvalidTokenError("token expired")
    except jwt.ImmatureSignatureError:
        raise jwt.InvalidTokenError("token not yet valid")
    except jwt.InvalidSignatureError:
        raise jwt.InvalidTokenError("invalid token signature")
    except Exception as exc:
        log_exception(...)
        raise jwt.InvalidTokenError(f"token verification failed: {str(exc)}")
```

**Zusätzlich in `.env` hinzufügen:**
```
SUPABASE_PROJECT_REF=your-project-ref
```

---

### Fix 2: Race Condition bei Session-Refresh
**Datei:** `backend/services/sync_runner.py`

**Aktuelles Problem:**
```python
except ServiceError as exc:
    if exc.status_code != 409:
        raise
    log_event(..., "sync.session_refresh_conflict", ...)
```

**Lösung:**
```python
def _build_authenticated_client(self, user_id: str, retry_count: int = 3):
    """Build authenticated client with retry logic for session conflicts."""
    account = self._store.fetch_account(user_id)
    if not account:
        raise ServiceError("Garmin account missing", status_code=400, category=ErrorCategory.AUTH)

    credentials = account.credentials()
    if not credentials:
        raise ServiceError("Garmin credentials missing", status_code=400, category=ErrorCategory.AUTH)

    email, password = credentials
    session_payload = account.session_payload()
    client = load_client(email=email, password=password, session_data=session_payload)

    refreshed_session = export_client_session(client)
    if not refreshed_session:
        return client, account

    # NEU: Retry-Logik für Session-Speicherung
    for attempt in range(retry_count):
        try:
            # Immer die aktuelle Version laden
            current_account = self._store.fetch_account(user_id)
            expected_version = current_account.garmin_session_version if current_account else None
            
            self._store.save_session_atomically(
                user_id,
                refreshed_session,
                expected_version=expected_version,
            )
            break  # Erfolg
        except ServiceError as exc:
            if exc.status_code == 409:  # Conflict
                if attempt < retry_count - 1:
                    # Kurz warten und erneut versuchen
                    import time
                    time.sleep(0.1 * (attempt + 1))
                    log_event(
                        self._logger,
                        logging.WARNING,
                        category=ErrorCategory.DB,
                        event="sync.session_refresh_retry",
                        message=f"Session refresh conflict, retry {attempt + 1}/{retry_count}",
                        user_id=user_id,
                    )
                    continue
                else:
                    # Letzter Versuch fehlgeschlagen
                    log_event(
                        self._logger,
                        logging.ERROR,
                        category=ErrorCategory.DB,
                        event="sync.session_refresh_failed",
                        message="Session refresh failed after all retries",
                        user_id=user_id,
                    )
                    # Trotzdem Client zurückgeben (Session ist funktional)
            else:
                raise  # Anderen Fehler weiterwerfen

    return client, account
```

---

### Fix 3: Legacy-Code entfernen
**Datei:** `static/dashboard/main.js`

**Aktion:** Funktion `legacyResolveActualSessionForPlanDate` komplett löschen (ca. 30 Zeilen)

**Suchen und löschen:**
```javascript
function legacyResolveActualSessionForPlanDate(payload) {
    // ... gesamte Funktion ...
}
```

---

## Priorität 2 (Kurzfristig)

### Fix 4: Auto-Sync Flag-Logik korrigieren
**Datei:** `static/dashboard/main.js`

**Aktuelles Problem:**
```javascript
let hasLoadedInitialDashboard = false;

// ...
if (_event === "SIGNED_IN" && hasLoadedInitialDashboard) {
    return;
}
// ...
if (state.currentSession?.access_token) {
    hasLoadedInitialDashboard = true;
}
```

**Lösung:**
```javascript
let hasLoadedInitialDashboard = false;

if (supabaseClient) {
    supabaseClient.auth.onAuthStateChange((_event, session) => {
        applyCurrentSession(session || null);
        
        // NEU: Explizite Behandlung verschiedener Events
        if (_event === "TOKEN_REFRESHED" || _event === "USER_UPDATED") {
            return;
        }

        // NEU: SIGNED_OUT setzt Flag zurück
        if (_event === "SIGNED_OUT") {
            hasLoadedInitialDashboard = false;
            clearPendingAuthProvider();
            setLoggedOutState();
            return;
        }

        // Verhindert redundanten Reload bei Tab-Fokus
        if (_event === "SIGNED_IN" && hasLoadedInitialDashboard) {
            return;
        }
        
        window.setTimeout(async () => {
            if (state.sessionRestorePending) {
                return;
            }
            if (state.currentSession?.access_token) {
                hasLoadedInitialDashboard = true;
                await refreshAppState({
                    requestedView: requestedAppViewFromPath(),
                    replaceHistory: true,
                    loadDashboardIfNeeded: true,
                });
            }
        }, 0);
    });
}
```

---

### Fix 5: Ladezustände verbessern
**Datei:** `templates/dashboard.html`

**Aktuelles Problem:**
```html
<span>Updating dashboard...</span>
```

**Lösung - HTML aktualisieren:**
```html
<div id="dashboardLoadingOverlay" class="dashboard-loading-overlay" hidden aria-hidden="true">
    <div class="dashboard-loading-indicator" role="status" aria-live="polite">
        <span class="dashboard-loading-spinner" aria-hidden="true"></span>
        <span id="dashboardLoadingText">Updating dashboard...</span>
        <div id="dashboardLoadingProgress" class="loading-progress" hidden>
            <div class="loading-progress-bar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
            <span class="loading-progress-text">0%</span>
        </div>
        <button id="dashboardLoadingCancel" class="btn btn-secondary btn-small" type="button" hidden>
            Cancel
        </button>
    </div>
</div>
```

**CSS hinzufügen (`static/dashboard.css`):**
```css
.loading-progress {
    width: 200px;
    margin-top: 12px;
}

.loading-progress-bar {
    height: 4px;
    background: var(--color-border);
    border-radius: 2px;
    overflow: hidden;
}

.loading-progress-bar::after {
    content: '';
    display: block;
    height: 100%;
    background: var(--color-primary);
    width: var(--progress-width, 0%);
    transition: width 0.3s ease;
}

.loading-progress-text {
    display: block;
    margin-top: 4px;
    font-size: 0.75rem;
    color: var(--color-muted);
}

.btn-small {
    padding: 4px 12px;
    font-size: 0.75rem;
    margin-top: 12px;
}
```

**JavaScript aktualisieren (`static/dashboard/main.js`):**
```javascript
// NEU: Loading-State-Management
const loadingState = {
    active: false,
    cancellable: false,
    onCancel: null,
    progress: 0,
    message: 'Loading...',
};

function setDashboardLoadingState(active, options = {}) {
    const overlay = el('dashboardLoadingOverlay');
    const text = el('dashboardLoadingText');
    const progressContainer = el('dashboardLoadingProgress');
    const cancelButton = el('dashboardLoadingCancel');
    
    if (!overlay) return;
    
    loadingState.active = active;
    loadingState.cancellable = options.cancellable || false;
    loadingState.onCancel = options.onCancel || null;
    loadingState.message = options.message || 'Updating dashboard...';
    
    if (active) {
        overlay.hidden = false;
        overlay.setAttribute('aria-hidden', 'false');
        if (text) text.textContent = loadingState.message;
        
        if (progressContainer && options.progress !== undefined) {
            progressContainer.hidden = false;
            updateLoadingProgress(options.progress);
        } else if (progressContainer) {
            progressContainer.hidden = true;
        }
        
        if (cancelButton) {
            cancelButton.hidden = !loadingState.cancellable;
        }
    } else {
        overlay.hidden = true;
        overlay.setAttribute('aria-hidden', 'true');
        loadingState.progress = 0;
    }
}

function updateLoadingProgress(percent) {
    const progressBar = el('dashboardLoadingProgress')?.querySelector('.loading-progress-bar');
    const progressText = el('dashboardLoadingProgress')?.querySelector('.loading-progress-text');
    
    if (progressBar) {
        progressBar.style.setProperty('--progress-width', `${percent}%`);
        progressBar.setAttribute('aria-valuenow', percent);
    }
    if (progressText) {
        progressText.textContent = `${Math.round(percent)}%`;
    }
}

function setLoadingMessage(message) {
    const text = el('dashboardLoadingText');
    if (text) text.textContent = message;
}

// Cancel-Button Event
const cancelLoadingBtn = el('dashboardLoadingCancel');
if (cancelLoadingBtn) {
    cancelLoadingBtn.addEventListener('click', () => {
        if (loadingState.cancellable && loadingState.onCancel) {
            loadingState.onCancel();
            setDashboardLoadingState(false);
        }
    });
}
```

---

### Fix 6: Error-Handling im Frontend verbessern
**Datei:** `static/dashboard/main.js`

**Aktuelles Problem:**
```javascript
const json = await response.json().catch(() => ({}));
```

**Lösung:**
```javascript
// NEU: Erweiterte API-Fehlerbehandlung
async function apiGet(url, options = {}) {
    const token = await getToken();
    const { timeout = 30000, retries = 0 } = options;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        // NEU: Explizites JSON-Parsing mit Fehlerbehandlung
        let json;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            try {
                json = await response.json();
            } catch (parseError) {
                throw new Error(`Invalid JSON response from ${url}: ${parseError.message}`);
            }
        } else {
            const text = await response.text();
            throw new Error(`Expected JSON response but got: ${text.substring(0, 100)}`);
        }
        
        if (!response.ok) {
            throw buildApiError(response, json);
        }
        
        return json;
    } catch (error) {
        clearTimeout(timeoutId);
        
        if (error.name === 'AbortError') {
            throw new Error(`Request to ${url} timed out after ${timeout}ms`);
        }
        
        // NEU: Retry-Logik für transient Errors
        if (retries > 0 && isTransientError(error)) {
            await sleep(1000);
            return apiGet(url, { ...options, retries: retries - 1 });
        }
        
        throw error;
    }
}

async function apiPost(url, body = null, options = {}) {
    const token = await getToken();
    const { timeout = 30000, retries = 0 } = options;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: body ? JSON.stringify(body) : null,
            signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        // NEU: Explizites JSON-Parsing
        let json;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            try {
                json = await response.json();
            } catch (parseError) {
                throw new Error(`Invalid JSON response from ${url}: ${parseError.message}`);
            }
        } else {
            const text = await response.text();
            throw new Error(`Expected JSON response but got: ${text.substring(0, 100)}`);
        }
        
        if (!response.ok) {
            throw buildApiError(response, json);
        }
        
        return json;
    } catch (error) {
        clearTimeout(timeoutId);
        
        if (error.name === 'AbortError') {
            throw new Error(`Request to ${url} timed out after ${timeout}ms`);
        }
        
        if (retries > 0 && isTransientError(error)) {
            await sleep(1000);
            return apiPost(url, body, { ...options, retries: retries - 1 });
        }
        
        throw error;
    }
}

// NEU: Hilfsfunktionen
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function isTransientError(error) {
    // Netzwerkfehler oder 5xx Server-Fehler sind transient
    if (error.message?.includes('Failed to fetch')) return true;
    if (error.message?.includes('NetworkError')) return true;
    if (error.status >= 500 && error.status < 600) return true;
    return false;
}

// NEU: Nutzerfreundliche Fehlermeldungen
function getUserFriendlyErrorMessage(error) {
    const message = error.message || 'Unknown error';
    
    if (message.includes('timed out')) {
        return 'The request took too long. Please check your connection and try again.';
    }
    if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
        return 'Unable to connect to the server. Please check your internet connection.';
    }
    if (message.includes('401') || message.includes('Unauthorized')) {
        return 'Your session has expired. Please sign in again.';
    }
    if (message.includes('403') || message.includes('Forbidden')) {
        return 'You do not have permission to perform this action.';
    }
    if (message.includes('404') || message.includes('Not Found')) {
        return 'The requested resource was not found.';
    }
    if (message.includes('500') || message.includes('Internal Server Error')) {
        return 'Something went wrong on our end. Please try again later.';
    }
    
    return message;
}

// NEU: Error-Display-Funktion
function showErrorToUser(error, context = '') {
    const friendlyMessage = getUserFriendlyErrorMessage(error);
    const fullMessage = context ? `${context}: ${friendlyMessage}` : friendlyMessage;
    
    // Nutzer benachrichtigen
    setGarminStatus(fullMessage);
    
    // Optional: Toast-Notification implementieren
    console.error('User-facing error:', error);
}
```

---

## Zusammenfassung

| Fix | Priorität | Aufwand | Auswirkung |
|-----|-----------|---------|------------|
| 1. JWT-Validierung | P1 | Gering | Hoch (Sicherheit) |
| 2. Race Condition | P1 | Mittel | Hoch (Stabilität) |
| 3. Legacy-Code | P1 | Gering | Niedrig (Wartbarkeit) |
| 4. Auto-Sync Flag | P2 | Gering | Mittel (UX) |
| 5. Ladezustände | P2 | Mittel | Hoch (UX) |
| 6. Error-Handling | P2 | Mittel | Hoch (UX) |

**Gesamtaufwand:** ca. 4-6 Stunden

**Testen nach Implementierung:**
1. Login/Logout mehrfach testen
2. Tab-Wechsel während Sync testen
3. Netzwerkfehler simulieren
4. Ladezustände bei verschiedenen Operationen prüfen
5. JWT mit verschiedenen Supabase-Projekten testen