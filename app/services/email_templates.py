from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import quote

from app.services.identity import get_identity_dict, resolve_public_app_url

# PulseDesk palette (matches dashboard.css) — solid colors only for email clients
BRAND = "#453a82"
BRAND_DEEP = "#322a62"
ACCENT = "#4f7cff"
BG = "#f3f5f9"
SURFACE = "#ffffff"
INK = "#1a2332"
MUTED = "#7a8699"
LINE = "#e8edf3"
WHITE = "#ffffff"


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def _branding() -> dict:
    identity = get_identity_dict()
    return {
        "app_name": identity.get("app_name") or "Project Management System",
        "brand_name": identity.get("brand_name") or "PulseDesk",
        "brand_mark": identity.get("brand_mark") or "PM",
        "brand_tagline": identity.get("brand_tagline") or "Project OS",
        "organization_name": identity.get("organization_name") or "Bank Sumut",
        "app_url": resolve_public_app_url(identity.get("app_url")),
    }


def _base_layout(*, title: str, preheader: str, body_html: str, footer_note: str) -> str:
    branding = _branding()
    app_name = escape(branding["app_name"])
    brand_name = escape(branding["brand_name"])
    brand_mark = escape(branding["brand_mark"])
    brand_tagline = escape(branding["brand_tagline"])
    organization = escape(branding["organization_name"])
    safe_title = escape(title)
    safe_preheader = escape(preheader)
    safe_footer = escape(footer_note)

    # Email-safe markup: tables + bgcolor + inline styles (no gradient/rgba).
    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="id">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{safe_title}</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: Arial, Helvetica, sans-serif !important; }}
  </style>
  <![endif]-->
</head>
<body style="margin:0;padding:0;background-color:{BG};">
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">
    {safe_preheader}
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}" style="background-color:{BG};margin:0;padding:0;width:100%;">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" bgcolor="{SURFACE}" style="width:560px;max-width:560px;background-color:{SURFACE};border:1px solid {LINE};border-collapse:separate;">
          <!-- Header -->
          <tr>
            <td bgcolor="{BRAND}" style="background-color:{BRAND};padding:0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BRAND}" style="background-color:{BRAND};">
                <tr>
                  <td width="18" style="font-size:0;line-height:0;">&nbsp;</td>
                  <td style="padding:22px 0;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="40" height="40" align="center" valign="middle" bgcolor="{BRAND_DEEP}" style="background-color:{BRAND_DEEP};width:40px;height:40px;color:{WHITE};font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:bold;border-radius:10px;">
                          {brand_mark}
                        </td>
                        <td width="12" style="font-size:0;line-height:0;">&nbsp;</td>
                        <td valign="middle" style="font-family:Arial,Helvetica,sans-serif;">
                          <div style="color:{WHITE};font-size:16px;font-weight:bold;line-height:1.2;mso-line-height-rule:exactly;">{brand_name}</div>
                          <div style="color:{WHITE};font-size:12px;line-height:1.4;padding-top:3px;mso-line-height-rule:exactly;">{brand_tagline} · {app_name}</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td width="18" style="font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td bgcolor="{SURFACE}" style="background-color:{SURFACE};padding:28px 28px 8px 28px;font-family:Arial,Helvetica,sans-serif;color:{INK};">
              {body_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td bgcolor="{SURFACE}" style="background-color:{SURFACE};padding:8px 28px 28px 28px;font-family:Arial,Helvetica,sans-serif;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td height="1" bgcolor="{LINE}" style="background-color:{LINE};font-size:0;line-height:0;height:1px;">&nbsp;</td>
                </tr>
              </table>
              <p style="margin:18px 0 0 0;font-size:12px;line-height:1.55;color:{MUTED};font-family:Arial,Helvetica,sans-serif;">{safe_footer}</p>
              <p style="margin:10px 0 0 0;font-size:11px;line-height:1.45;color:{MUTED};font-family:Arial,Helvetica,sans-serif;">
                Email otomatis dari sistem. Mohon tidak membalas pesan ini.
              </p>
            </td>
          </tr>
        </table>
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width:560px;max-width:560px;">
          <tr>
            <td align="center" style="padding:16px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUTED};">
              {organization} · {brand_name} Notification
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta_button(label: str, url: str) -> str:
    safe_url = escape(url, quote=True)
    safe_label = escape(label)
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0 8px 0;">
      <tr>
        <td align="left" bgcolor="{ACCENT}" style="background-color:{ACCENT};border-radius:10px;">
          <a href="{safe_url}" target="_blank"
             style="display:inline-block;padding:12px 22px;color:{WHITE};text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:bold;">
            {safe_label}
          </a>
        </td>
      </tr>
    </table>
    """


def _detail_row(label: str, value: str, *, last: bool = False) -> str:
    border = "" if last else f"border-bottom:1px solid {LINE};"
    return f"""
    <tr>
      <td width="38%" valign="top" style="padding:10px 14px;width:38%;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{MUTED};{border}">
        {escape(label)}
      </td>
      <td valign="top" style="padding:10px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{INK};font-weight:bold;{border}">
        {escape(value)}
      </td>
    </tr>
    """


def welcome_user_email(
    *,
    name: str,
    email: str,
    temporary_password: str,
    login_url: str | None = None,
) -> EmailContent:
    branding = _branding()
    if login_url and login_url.strip().lower().startswith(("http://", "https://")):
        raw = login_url.strip().rstrip("/")
        url = raw if raw.endswith("/login") else f"{resolve_public_app_url(raw)}/login"
    else:
        url = f"{resolve_public_app_url(branding['app_url'])}/login"
    safe_name = name.strip() or "Pengguna"
    brand_name = branding["brand_name"]
    app_name = branding["app_name"]

    subject = f"Selamat datang di {brand_name}, {safe_name}"
    text = (
        f"Halo {safe_name},\n\n"
        f"Akun Anda di {app_name} telah dibuat.\n\n"
        f"Email: {email}\n"
        f"Password sementara: {temporary_password}\n\n"
        f"Silakan masuk di {url} dan segera ganti password Anda.\n\n"
        f"Salam,\nTim {brand_name}"
    )

    body = f"""
      <h1 style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:22px;line-height:1.3;color:{INK};font-weight:bold;">
        Selamat datang, {escape(safe_name)}
      </h1>
      <p style="margin:0 0 16px 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:{MUTED};">
        Akun Anda di <strong style="color:{INK};">{escape(app_name)}</strong> sudah siap digunakan.
        Gunakan kredensial di bawah ini untuk masuk pertama kali.
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}"
        style="width:100%;background-color:{BG};border:1px solid {LINE};border-collapse:separate;">
        {_detail_row("Nama", safe_name)}
        {_detail_row("Email", email)}
        {_detail_row("Password sementara", temporary_password, last=True)}
      </table>
      {_cta_button("Silahkan Login", url)}
      <p style="margin:14px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.55;color:{MUTED};">
        Demi keamanan, segera ganti password setelah login berhasil.
      </p>
    """

    html = _base_layout(
        title=subject,
        preheader=f"Akun {brand_name} Anda telah dibuat. Login dengan password sementara.",
        body_html=body,
        footer_note="Jika Anda tidak merasa didaftarkan, abaikan email ini atau hubungi administrator.",
    )
    return EmailContent(subject=subject, text=text, html=html)


def new_device_confirmation_email(
    *,
    name: str,
    email: str,
    device_label: str,
    browser_name: str,
    os_name: str,
    ip_address: str | None,
    confirm_url: str,
    expires_minutes: int = 30,
) -> EmailContent:
    branding = _branding()
    safe_name = name.strip() or "Pengguna"
    brand_name = branding["brand_name"]
    app_name = branding["app_name"]
    device_text = device_label or f"{browser_name} di {os_name}"
    ip_text = ip_address or "-"

    subject = f"Konfirmasi perangkat baru · {brand_name}"
    text = (
        f"Halo {safe_name},\n\n"
        f"Kami mendeteksi percobaan login ke {app_name} dari perangkat yang belum dipercaya.\n\n"
        f"Perangkat: {device_text}\n"
        f"Browser: {browser_name or '-'}\n"
        f"Sistem: {os_name or '-'}\n"
        f"IP: {ip_text}\n"
        f"Akun: {email}\n\n"
        f"Jika ini Anda, konfirmasi perangkat lewat tautan berikut "
        f"(berlaku {expires_minutes} menit):\n{confirm_url}\n\n"
        f"Jika bukan Anda, abaikan email ini dan segera amankan akun Anda.\n\n"
        f"Salam,\nTim {brand_name}"
    )

    body = f"""
      <h1 style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:22px;line-height:1.3;color:{INK};font-weight:bold;">
        Konfirmasi perangkat baru
      </h1>
      <p style="margin:0 0 16px 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:{MUTED};">
        Halo <strong style="color:{INK};">{escape(safe_name)}</strong>, ada percobaan login ke
        <strong style="color:{INK};">{escape(app_name)}</strong> dari perangkat yang belum terdaftar
        atau cookie perangkatnya hilang (misalnya setelah clear cache).
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}"
        style="width:100%;background-color:{BG};border:1px solid {LINE};border-collapse:separate;">
        {_detail_row("Perangkat", device_text)}
        {_detail_row("Browser", browser_name or "-")}
        {_detail_row("Sistem operasi", os_name or "-")}
        {_detail_row("Alamat IP", ip_text)}
        {_detail_row("Akun", email, last=True)}
      </table>
      {_cta_button("Ya, ini saya — percaya perangkat ini", confirm_url)}
      <p style="margin:14px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.55;color:{MUTED};">
        Tautan berlaku {expires_minutes} menit. Jika tombol tidak berfungsi, salin tautan ini:<br />
        <a href="{escape(confirm_url, quote=True)}" style="color:{ACCENT};word-break:break-all;">{escape(confirm_url)}</a>
      </p>
    """

    html = _base_layout(
        title=subject,
        preheader="Login dari perangkat baru memerlukan konfirmasi Anda.",
        body_html=body,
        footer_note="Jika Anda tidak mencoba login, abaikan email ini. Jangan bagikan tautan konfirmasi kepada siapa pun.",
    )
    return EmailContent(subject=subject, text=text, html=html)


def reset_password_email(
    *,
    name: str,
    email: str,
    reset_url: str | None = None,
    reset_token: str | None = None,
    expires_minutes: int = 60,
) -> EmailContent:
    branding = _branding()
    safe_name = name.strip() or "Pengguna"
    brand_name = branding["brand_name"]

    if reset_url:
        url = reset_url
    else:
        token = reset_token or "TOKEN"
        url = f"{branding['app_url']}/reset-password?token={quote(token)}&email={quote(email)}"

    subject = f"Reset password {brand_name}"
    text = (
        f"Halo {safe_name},\n\n"
        f"Kami menerima permintaan reset password untuk akun {email}.\n"
        f"Buka tautan berikut untuk membuat password baru (berlaku {expires_minutes} menit):\n"
        f"{url}\n\n"
        f"Jika Anda tidak meminta reset password, abaikan email ini.\n\n"
        f"Salam,\nTim {brand_name}"
    )

    body = f"""
      <h1 style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:22px;line-height:1.3;color:{INK};font-weight:bold;">
        Reset password Anda
      </h1>
      <p style="margin:0 0 16px 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:{MUTED};">
        Halo <strong style="color:{INK};">{escape(safe_name)}</strong>, kami menerima permintaan untuk
        mengatur ulang password akun <strong style="color:{INK};">{escape(email)}</strong>.
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}"
        style="width:100%;background-color:{BG};border:1px solid {LINE};border-collapse:separate;">
        <tr>
          <td style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.55;color:{INK};">
            Tautan reset berlaku selama <strong>{expires_minutes} menit</strong>.
            Setelah itu, Anda perlu meminta reset ulang.
          </td>
        </tr>
      </table>
      {_cta_button("Buat Password Baru", url)}
      <p style="margin:14px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.55;color:{MUTED};">
        Jika tombol tidak berfungsi, salin tautan ini ke browser:<br />
        <a href="{escape(url, quote=True)}" style="color:{ACCENT};word-break:break-all;">{escape(url)}</a>
      </p>
    """

    html = _base_layout(
        title=subject,
        preheader=f"Tautan reset password berlaku {expires_minutes} menit.",
        body_html=body,
        footer_note="Jika Anda tidak meminta reset password, abaikan email ini. Akun Anda tetap aman.",
    )
    return EmailContent(subject=subject, text=text, html=html)
