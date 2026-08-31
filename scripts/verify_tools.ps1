# Check the deployed tool endpoints end to end.
#
#   .\scripts\verify_tools.ps1            safe checks only, sends nothing
#   .\scripts\verify_tools.ps1 -SendReal  also sends one real WhatsApp to -Phone
#
# The secret is read from .env so it never has to be pasted or shell-quoted.

param(
    [string]$BaseUrl = "https://elevatebox-voice-agent-production.up.railway.app",
    [switch]$SendReal,
    [string]$Phone = "+917887083856"
)

$ErrorActionPreference = "Stop"

$envPath = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envPath)) { Write-Error "no .env at $envPath"; exit 1 }

$secret = (Get-Content $envPath |
    Where-Object { $_ -match '^\s*SARVAM_TOOL_SECRET\s*=' } |
    ForEach-Object { ($_ -split '=', 2)[1].Trim() } |
    Select-Object -First 1)
if (-not $secret) { Write-Error "SARVAM_TOOL_SECRET not found in .env"; exit 1 }

$auth = @{ "Content-Type" = "application/json"; "X-Tool-Secret" = $secret }

function Show($label, $code, $body) {
    $colour = if ($code -eq 200 -or $code -eq 401 -or $code -eq 422) { "Green" } else { "Red" }
    Write-Host ("  {0,-34} " -f $label) -NoNewline
    Write-Host ("[{0}] " -f $code) -ForegroundColor $colour -NoNewline
    Write-Host $body
}

# Invoke-RestMethod throws on any non-2xx, and a 401 here is a pass, so the
# status code has to be recovered from the exception rather than the result.
function Hit($label, $path, $headers, $json) {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl$path" -Method Post -Headers $headers `
             -Body $json -UseBasicParsing -TimeoutSec 30
        Show $label $r.StatusCode $r.Content
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            $code = [int]$resp.StatusCode
            $text = (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
            Show $label $code $text
        } else { Show $label "ERR" $_.Exception.Message }
    }
}

Write-Host "`nBase: $BaseUrl" -ForegroundColor Cyan
Write-Host "Secret loaded from .env (length $($secret.Length))`n" -ForegroundColor Cyan

Write-Host "1. Is it up?" -ForegroundColor Yellow
try {
    $h = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 30
    Show "GET /health" $h.StatusCode $h.Content
} catch { Show "GET /health" "ERR" $_.Exception.Message }

Write-Host "`n2. Is the secret enforced?  (401 = good)" -ForegroundColor Yellow
$body = '{"call_id":"verify-1","phone":"' + $Phone + '","requested_expression":"kal"}'
Hit "no header"    "/tools/schedule-callback" @{ "Content-Type" = "application/json" } $body
Hit "wrong secret" "/tools/schedule-callback" `
    @{ "Content-Type" = "application/json"; "X-Tool-Secret" = "wrong" } $body

Write-Host "`n3. Does the secret work?  (structured error = good, writes nothing)" -ForegroundColor Yellow
Hit "valid secret, no callback_time" "/tools/schedule-callback" $auth $body
Hit "missing call_id -> 422"         "/tools/complete-call" $auth '{"phone":"8688664337"}'

if ($SendReal) {
    Write-Host "`n4. Real WhatsApp to $Phone" -ForegroundColor Yellow
    $id = "verify-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $payload = '{"call_id":"' + $id + '","phone":"' + $Phone +
               '","business_type":"fashion","product_count":"150",' +
               '"required_features":["payment gateway"],"budget_range":"80k",' +
               '"timeline":"six weeks","summary":"Verification message."}'
    Hit "send (first time)" "/tools/send-high-intent-whatsapp" $auth $payload
    Hit "send again (same call_id)" "/tools/send-high-intent-whatsapp" $auth $payload
    Write-Host "  second call must say already_sent:true and send nothing" -ForegroundColor DarkGray
} else {
    Write-Host "`n4. Real WhatsApp  -  skipped. Add -SendReal to actually send one." -ForegroundColor DarkGray
}

Write-Host ""
