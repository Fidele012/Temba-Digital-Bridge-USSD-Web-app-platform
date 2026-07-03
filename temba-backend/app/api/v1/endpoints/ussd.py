"""
Africa's Talking USSD callback - fully bilingual (English / Kinyarwanda).

USSD navigation encoding:
  text = "<lang>*<route>*..."

  parts[0] = language choice  (1=EN, 2=RW)
  parts[1] = auth route       (1=Register, 2=Login, 0=Exit)

── REGISTER FLOW (route == "1") ──────────────────────────────────────────────
  parts[2]  = full name
  parts[3]  = province (1-5)
  parts[4]  = district (1-N)
  parts[5]  = sector   (text, "0" to skip)
  parts[6]  = cell     (text, "0" to skip)
  parts[7]  = village  (text, "0" to skip)
  parts[8]  = SMS phone number ("0" = use calling number)
  parts[9]  = create 4-digit PIN
  parts[10] = confirm PIN
  → Account created; dial again to use services.

── LOGIN FLOW (route == "2") ─────────────────────────────────────────────────
  parts[2] = 4-digit USSD PIN
  parts[3] = main menu choice (1-6, 0=Exit)
  parts[4+]= sub-navigation for selected service

  Main menu:
    1. Report water issue
    2. Track my reports
    3. Book appointment
    4. My appointments
    5. Service request status
    6. Submit service request

── PIN SETUP (existing web user, no USSD PIN yet) ───────────────────────────
  Triggered automatically under Login route when ussd_pin_hash is None:
  parts[2] = new 4-digit PIN
  parts[3] = confirm PIN
"""
from __future__ import annotations

import asyncio
import random
import re
import secrets
import string
from datetime import date, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.services.notification_service import notify_user, send_sms_background
from app.models.appointment import (
    Appointment,
    AppointmentReason,
    AppointmentStatus,
    MeetingType,
)
from app.models.provider import Provider, ProviderStatus
from app.models.report import Report, ReportCategory, ReportStatus, ReportUrgency
from app.models.service_request import (
    ServiceRequest,
    ServiceRequestType,
    ServiceRequestUrgency,
)
from app.models.user import User, UserRole

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/ussd", tags=["ussd"])


def _phone_variants(phone: str) -> list[str]:
    """Return all common storage formats of a Rwanda phone number."""
    p = re.sub(r"[\s\-]", "", phone)
    variants: set[str] = {p}
    if p.startswith("+250") and len(p) >= 12:
        variants.update({"0" + p[4:], "250" + p[4:]})
    elif p.startswith("250") and len(p) == 12:
        variants.update({"+" + p, "0" + p[3:]})
    elif p.startswith("0") and len(p) == 10:
        variants.update({"+250" + p[1:], "250" + p[1:]})
    return list(variants)


# ── Rwanda Administrative Hierarchy ──────────────────────────────────────────
# Province list (index 0-4 maps to choice "1"-"5")
_PROVINCES_LIST: list[str] = [
    "Kigali City",
    "Northern Province",
    "Southern Province",
    "Eastern Province",
    "Western Province",
]

# Districts per province (province choice "1"-"5" → district list)
_DISTRICTS: dict[str, list[str]] = {
    "1": ["Gasabo", "Kicukiro", "Nyarugenge"],
    "2": ["Burera", "Gakenke", "Gicumbi", "Musanze", "Rulindo"],
    "3": ["Gisagara", "Huye", "Kamonyi", "Muhanga", "Nyamagabe", "Nyanza", "Nyaruguru", "Ruhango"],
    "4": ["Bugesera", "Gatsibo", "Kayonza", "Kirehe", "Ngoma", "Nyagatare", "Rwamagana"],
    "5": ["Karongi", "Ngororero", "Nyabihu", "Nyamasheke", "Rubavu", "Rutsiro", "Rusizi"],
}

# Sectors per district → cells per sector
# _RW[district][sector] = [cell, ...]
_RW: dict[str, dict[str, list[str]]] = {
    # ── Kigali City ──────────────────────────────────────────────────────────
    "Gasabo": {
        "Bumbogo":    ["Bidudu","Cyarubare","Gasagara","Kagugu","Ntarama","Rubaya"],
        "Gatsata":    ["Bibare","Gisanga","Gitega","Kagugu","Murundo","Ntarama"],
        "Gikomero":   ["Birunga","Burega","Gacurabwenge","Gikomero","Kabuye","Kagina"],
        "Gisozi":     ["Bidudu","Gasagara","Gisozi","Murambi","Rugenge","Rusororo"],
        "Jabana":     ["Bwiza","Gasagara","Jabana","Karuruma","Mburabuturo","Nyagatovu"],
        "Jali":       ["Bukirwa","Gasharu","Jali","Kabuga","Rubungo","Rutonde"],
        "Kacyiru":    ["Kamatamu","Kacyiru","Kamutwa","Kibagabaga","Nyarutarama"],
        "Kimihurura": ["Gikondo","Kagugu","Kimihurura","Rugando"],
        "Kimironko":  ["Bibare","Kanzenze","Kimironko","Mageragere","Rukiri"],
        "Kinyinya":   ["Kabuyange","Kinyinya","Murama","Nyirangarama","Rukuri"],
        "Ndera":      ["Kagugu","Musenyi","Ndera","Rutonde"],
        "Nduba":      ["Busenyi","Kagugu","Nduba","Rurimbi"],
        "Remera":     ["Gisimenti","Nyabisindu","Odesha","Rukiri"],
        "Rusororo":   ["Bumbogo","Gasagara","Karuruma","Ntarama","Rusororo"],
        "Rutunga":    ["Bidudu","Kagina","Murambi","Rutunga"],
    },
    "Kicukiro": {
        "Gahanga":    ["Biryogo","Cyimo","Gahanga","Kibirizi","Ruhuha"],
        "Gatenga":    ["Gatenga","Kabarondo","Kagugu","Kibirizi","Nyabisindu"],
        "Gikondo":    ["Biryogo","Gikondo","Kagugu","Rugunga"],
        "Kagarama":   ["Kagarama","Kibagabaga","Nyanza","Rugunga"],
        "Kanombe":    ["Gikondo","Kanombe","Kibagabaga","Nyarugunga"],
        "Kicukiro":   ["Kicukiro","Niboye","Nyarugunga","Rwezamenyo"],
        "Masaka":     ["Kabuye","Masaka","Nzige","Rugunga"],
        "Niboye":     ["Kibirizi","Niboye","Ruhuha","Rutunga"],
        "Nyarugunga": ["Kadahokwa","Nyarugunga","Rugunga","Rusororo"],
        "Rubilizi":   ["Gikomero","Nyarugenge","Rubilizi","Rusororo"],
    },
    "Nyarugenge": {
        "Gitega":     ["Biryogo","Gitega","Kagugu","Nyarutarama"],
        "Kanyinya":   ["Bidudu","Gikondo","Kanyinya","Murambi"],
        "Kigali":     ["Biryogo","Kigali","Rugenge","Rwezamenyo"],
        "Kimisagara": ["Kimisagara","Muhima","Nyabugogo","Rugenge"],
        "Mageragere": ["Biryogo","Mageragere","Rugunga","Rusororo"],
        "Muhima":     ["Muhima","Nyamirambo","Rugenge","Rwezamenyo"],
        "Nyakabanda": ["Biryogo","Kibirizi","Nyakabanda","Rugunga"],
        "Nyamirambo": ["Biryogo","Gikondo","Nyamirambo","Rugunga"],
        "Nyarugenge": ["Kagugu","Nyarugenge","Rugenge","Rwezamenyo"],
        "Rwezamenyo": ["Biryogo","Kagugu","Rugunga","Rwezamenyo"],
    },
    # ── Northern Province ─────────────────────────────────────────────────────
    "Burera": {
        "Bungwe":      ["Bungwe","Gasura","Kizi","Rugeshi","Rwamiko"],
        "Butaro":      ["Buhanga","Butaro","Cyabingo","Rugeshi","Rwamiko"],
        "Cyanika":     ["Cyanika","Gasura","Kizi","Mugera","Rwamiko"],
        "Cyeru":       ["Cyeru","Gasura","Kizi","Rugeshi","Rweza"],
        "Gahunga":     ["Cyabingo","Gahunga","Gasura","Rugeshi","Rwamiko"],
        "Gatebe":      ["Cyabingo","Gasura","Gatebe","Kizi","Rugeshi"],
        "Gitovu":      ["Cyabingo","Gasura","Gitovu","Kizi","Rugeshi"],
        "Kagogo":      ["Cyabingo","Gasura","Kagogo","Kizi","Rugeshi"],
        "Kinoni":      ["Cyabingo","Gasura","Kinoni","Kizi","Rugeshi"],
        "Kivuye":      ["Cyabingo","Gasura","Kivuye","Kizi","Rugeshi"],
        "Nemba":       ["Cyabingo","Gasura","Nemba","Rugeshi","Rwamiko"],
        "Rugarama":    ["Cyabingo","Gasura","Rugeshi","Rugarama","Rwamiko"],
        "Rugendabari": ["Cyabingo","Gasura","Kizi","Rugendabari","Rugeshi"],
        "Ruhunde":     ["Cyabingo","Gasura","Kizi","Rugeshi","Ruhunde"],
        "Rusarabuye":  ["Cyabingo","Gasura","Kizi","Rugeshi","Rusarabuye"],
        "Rwerere":     ["Cyabingo","Gasura","Kizi","Rugeshi","Rwerere"],
    },
    "Gakenke": {
        "Busengo":   ["Busengo","Cyabingo","Gasura","Kizi","Rugeshi"],
        "Coko":      ["Coko","Cyabingo","Gasura","Kizi","Rugeshi"],
        "Cyabingo":  ["Cyabingo","Gasura","Kizi","Mugera","Rwamiko"],
        "Gakenke":   ["Cyabingo","Gakenke","Gasura","Kizi","Rugeshi"],
        "Gashenyi":  ["Cyabingo","Gashenyi","Gasura","Kizi","Rugeshi"],
        "Janja":     ["Cyabingo","Gasura","Janja","Kizi","Rugeshi"],
        "Kamubuga":  ["Cyabingo","Gasura","Kamubuga","Kizi","Rugeshi"],
        "Karambi":   ["Cyabingo","Gasura","Karambi","Kizi","Rugeshi"],
        "Kayonga":   ["Cyabingo","Gasura","Kayonga","Kizi","Rugeshi"],
        "Minazi":    ["Cyabingo","Gasura","Kizi","Minazi","Rugeshi"],
        "Muhondo":   ["Cyabingo","Gasura","Kizi","Muhondo","Rugeshi"],
        "Mukarange": ["Cyabingo","Gasura","Kizi","Mukarange","Rugeshi"],
        "Musasa":    ["Cyabingo","Gasura","Kizi","Musasa","Rugeshi"],
        "Muzo":      ["Cyabingo","Gasura","Kizi","Muzo","Rugeshi"],
        "Nemba":     ["Cyabingo","Gasura","Kizi","Nemba","Rugeshi"],
        "Ruli":      ["Cyabingo","Gasura","Kizi","Rugeshi","Ruli"],
        "Rusasa":    ["Cyabingo","Gasura","Kizi","Rugeshi","Rusasa"],
        "Rushashi":  ["Cyabingo","Gasura","Kizi","Rugeshi","Rushashi"],
    },
    "Gicumbi": {
        "Bukure":      ["Bukure","Cyabingo","Gasura","Kizi","Rugeshi"],
        "Bwisige":     ["Bwisige","Cyabingo","Gasura","Kizi","Rugeshi"],
        "Byumba":      ["Byumba","Cyabingo","Gasura","Kizi","Rugeshi"],
        "Cyumba":      ["Cyabingo","Cyumba","Gasura","Kizi","Rugeshi"],
        "Gicumbi":     ["Cyabingo","Gasura","Gicumbi","Kizi","Rugeshi"],
        "Gosho":       ["Cyabingo","Gasura","Gosho","Kizi","Rugeshi"],
        "Kaniga":      ["Cyabingo","Gasura","Kaniga","Kizi","Rugeshi"],
        "Manyagiro":   ["Cyabingo","Gasura","Kizi","Manyagiro","Rugeshi"],
        "Miyove":      ["Cyabingo","Gasura","Kizi","Miyove","Rugeshi"],
        "Mukono":      ["Cyabingo","Gasura","Kizi","Mukono","Rugeshi"],
        "Mutete":      ["Cyabingo","Gasura","Kizi","Mutete","Rugeshi"],
        "Nyamiyaga":   ["Cyabingo","Gasura","Kizi","Nyamiyaga","Rugeshi"],
        "Nyankenke":   ["Cyabingo","Gasura","Kizi","Nyankenke","Rugeshi"],
        "Rubaya":      ["Cyabingo","Gasura","Kizi","Rubaya","Rugeshi"],
        "Rugabano":    ["Cyabingo","Gasura","Kizi","Rugabano","Rugeshi"],
        "Rugali":      ["Cyabingo","Gasura","Kizi","Rugali","Rugeshi"],
        "Ruhondo":     ["Cyabingo","Gasura","Kizi","Rugeshi","Ruhondo"],
        "Rusiga":      ["Cyabingo","Gasura","Kizi","Rugeshi","Rusiga"],
        "Tanda":       ["Cyabingo","Gasura","Kizi","Rugeshi","Tanda"],
        "Wimana":      ["Cyabingo","Gasura","Kizi","Rugeshi","Wimana"],
    },
    "Musanze": {
        "Busogo":    ["Busogo","Cyabashuri","Mubuga","Nkanka","Rususa"],
        "Cyuve":     ["Cyuve","Kiyumba","Nkotsi","Rwaza","Sarangi"],
        "Gacaca":    ["Bitare","Gacaca","Karwasa","Nyagisozi","Remera"],
        "Gashaki":   ["Gashaki","Kagano","Karwasa","Nyundo","Rwaza"],
        "Gataraga":  ["Gataraga","Kagano","Murambi","Nyundo","Shingiro"],
        "Kimonyi":   ["Biruyi","Kimonyi","Nyundo","Ruganda","Ryabega"],
        "Kinigi":    ["Bisizi","Cyanzarwe","Kinigi","Nyabigoma","Nyamyumba"],
        "Muhoza":    ["Busogo","Muganwa","Muhoza","Nyundo","Rutonde"],
        "Muko":      ["Busenyi","Kageyo","Mukarange","Muko","Nyabirasi"],
        "Musanze":   ["Mpenge","Musanze","Nyabugogo","Rugarama","Ruhondo"],
        "Nkotsi":    ["Gasura","Kabuye","Murambi","Nkotsi","Nyundo"],
        "Nyange":    ["Gasura","Kagano","Kizi","Nyange","Rugeshi"],
        "Remera":    ["Gasura","Kagano","Kizi","Remera","Rugeshi"],
        "Rwaza":     ["Cyabingo","Gasura","Kizi","Rugeshi","Rwaza"],
        "Shingiro":  ["Gasura","Kagano","Kizi","Rugeshi","Shingiro"],
    },
    "Rulindo": {
        "Base":        ["Base","Gasura","Kizi","Mugera","Rwamiko"],
        "Burega":      ["Burega","Gasura","Kizi","Rugeshi","Rwamiko"],
        "Bushoki":     ["Bushoki","Gasura","Kizi","Rugeshi","Rwamiko"],
        "Buyoga":      ["Buyoga","Gasura","Kizi","Rugeshi","Rwamiko"],
        "Cyinzuzi":    ["Cyinzuzi","Gasura","Kizi","Rugeshi","Rwamiko"],
        "Cyungo":      ["Cyungo","Gasura","Kizi","Rugeshi","Rwamiko"],
        "Kinihira":    ["Gasura","Kinihira","Kizi","Rugeshi","Rwamiko"],
        "Kisaro":      ["Gasura","Kisaro","Kizi","Rugeshi","Rwamiko"],
        "Masoro":      ["Gasura","Kizi","Masoro","Rugeshi","Rwamiko"],
        "Mbogo":       ["Gasura","Kizi","Mbogo","Rugeshi","Rwamiko"],
        "Murambi":     ["Gasura","Kizi","Murambi","Rugeshi","Rwamiko"],
        "Ngoma":       ["Gasura","Kizi","Ngoma","Rugeshi","Rwamiko"],
        "Ntarabana":   ["Gasura","Kizi","Ntarabana","Rugeshi","Rwamiko"],
        "Rukomangwa":  ["Gasura","Kizi","Rugeshi","Rukomangwa","Rwamiko"],
        "Rusiga":      ["Gasura","Kizi","Rugeshi","Rusiga","Rwamiko"],
        "Shyorongi":   ["Gasura","Kizi","Rugeshi","Rwamiko","Shyorongi"],
        "Tumba":       ["Gasura","Kizi","Rugeshi","Rwamiko","Tumba"],
    },
    # ── Southern Province ─────────────────────────────────────────────────────
    "Gisagara": {
        "Gikonko":  ["Gasura","Gikonko","Kizi","Mugera","Rwamiko"],
        "Gishubi":  ["Gasura","Gishubi","Kizi","Mugera","Rwamiko"],
        "Kansi":    ["Gasura","Kansi","Kizi","Mugera","Rwamiko"],
        "Kibirizi": ["Gasura","Kibirizi","Kizi","Mugera","Rwamiko"],
        "Kigembe":  ["Gasura","Kigembe","Kizi","Mugera","Rwamiko"],
        "Mamba":    ["Gasura","Kizi","Mamba","Mugera","Rwamiko"],
        "Muganza":  ["Gasura","Kizi","Muganza","Mugera","Rwamiko"],
        "Mugombwa": ["Gasura","Kizi","Mugera","Mugombwa","Rwamiko"],
        "Mukindo":  ["Gasura","Kizi","Mugera","Mukindo","Rwamiko"],
        "Musha":    ["Gasura","Kizi","Mugera","Musha","Rwamiko"],
        "Ndora":    ["Gasura","Kizi","Mugera","Ndora","Rwamiko"],
        "Nyanza":   ["Gasura","Kizi","Mugera","Nyanza","Rwamiko"],
        "Save":     ["Gasura","Kizi","Mugera","Rwamiko","Save"],
    },
    "Huye": {
        "Gishamvu": ["Gasura","Gishamvu","Kizi","Mugera","Rwamiko"],
        "Huye":     ["Gasura","Huye","Kizi","Mugera","Rwamiko"],
        "Karama":   ["Gasura","Karama","Kizi","Mugera","Rwamiko"],
        "Kigoma":   ["Gasura","Kigoma","Kizi","Mugera","Rwamiko"],
        "Kinazi":   ["Gasura","Kinazi","Kizi","Mugera","Rwamiko"],
        "Maraba":   ["Gasura","Kizi","Maraba","Mugera","Rwamiko"],
        "Mbazi":    ["Gasura","Kizi","Mbazi","Mugera","Rwamiko"],
        "Mukura":   ["Gasura","Kizi","Mugera","Mukura","Rwamiko"],
        "Ngoma":    ["Gasura","Kizi","Mugera","Ngoma","Rwamiko"],
        "Ruhashya": ["Gasura","Kizi","Mugera","Ruhashya","Rwamiko"],
        "Rusatira": ["Gasura","Kizi","Mugera","Rusatira","Rwamiko"],
        "Rwaniro":  ["Gasura","Kizi","Mugera","Rwamiko","Rwaniro"],
        "Simbi":    ["Gasura","Kizi","Mugera","Rwamiko","Simbi"],
        "Tumba":    ["Gasura","Kizi","Mugera","Rwamiko","Tumba"],
    },
    "Kamonyi": {
        "Gacurabwenge": ["Gasura","Gacurabwenge","Kizi","Mugera","Rwamiko"],
        "Karama":       ["Gasura","Karama","Kizi","Mugera","Rwamiko"],
        "Kayenzi":      ["Gasura","Kayenzi","Kizi","Mugera","Rwamiko"],
        "Kayumbu":      ["Gasura","Kayumbu","Kizi","Mugera","Rwamiko"],
        "Mugina":       ["Gasura","Kizi","Mugera","Mugina","Rwamiko"],
        "Musambira":    ["Gasura","Kizi","Mugera","Musambira","Rwamiko"],
        "Ngamba":       ["Gasura","Kizi","Mugera","Ngamba","Rwamiko"],
        "Nyamiyaga":    ["Gasura","Kizi","Mugera","Nyamiyaga","Rwamiko"],
        "Nyarubaka":    ["Gasura","Kizi","Mugera","Nyarubaka","Rwamiko"],
        "Rugalika":     ["Gasura","Kizi","Mugera","Rugalika","Rwamiko"],
        "Rugarika":     ["Gasura","Kizi","Mugera","Rugarika","Rwamiko"],
        "Rukoma":       ["Gasura","Kizi","Mugera","Rukoma","Rwamiko"],
        "Runda":        ["Gasura","Kizi","Mugera","Rwamiko","Runda"],
    },
    "Muhanga": {
        "Cyeza":       ["Cyeza","Gasura","Kizi","Mugera","Rwamiko"],
        "Kabacuzi":    ["Gasura","Kabacuzi","Kizi","Mugera","Rwamiko"],
        "Kibangu":     ["Gasura","Kibangu","Kizi","Mugera","Rwamiko"],
        "Kiyumba":     ["Gasura","Kiyumba","Kizi","Mugera","Rwamiko"],
        "Muhanga":     ["Gasura","Kizi","Mugera","Muhanga","Rwamiko"],
        "Mushishiro":  ["Gasura","Kizi","Mugera","Mushishiro","Rwamiko"],
        "Nyabinoni":   ["Gasura","Kizi","Mugera","Nyabinoni","Rwamiko"],
        "Nyamabuye":   ["Gasura","Kizi","Mugera","Nyamabuye","Rwamiko"],
        "Nyamariza":   ["Gasura","Kizi","Mugera","Nyamariza","Rwamiko"],
        "Rongi":       ["Gasura","Kizi","Mugera","Rongi","Rwamiko"],
        "Rugendabari": ["Gasura","Kizi","Mugera","Rugendabari","Rwamiko"],
    },
    "Nyamagabe": {
        "Buruhukiro": ["Buruhukiro","Gasura","Kizi","Mugera","Rwamiko"],
        "Cyanika":    ["Cyanika","Gasura","Kizi","Mugera","Rwamiko"],
        "Gasaka":     ["Gasaka","Gasura","Kizi","Mugera","Rwamiko"],
        "Gatare":     ["Gasura","Gatare","Kizi","Mugera","Rwamiko"],
        "Kaduha":     ["Gasura","Kaduha","Kizi","Mugera","Rwamiko"],
        "Kamegeri":   ["Gasura","Kamegeri","Kizi","Mugera","Rwamiko"],
        "Kibirizi":   ["Gasura","Kibirizi","Kizi","Mugera","Rwamiko"],
        "Kibumbwe":   ["Gasura","Kibumbwe","Kizi","Mugera","Rwamiko"],
        "Kitabi":     ["Gasura","Kitabi","Kizi","Mugera","Rwamiko"],
        "Mbazi":      ["Gasura","Kizi","Mbazi","Mugera","Rwamiko"],
        "Mugano":     ["Gasura","Kizi","Mugano","Mugera","Rwamiko"],
        "Musange":    ["Gasura","Kizi","Mugera","Musange","Rwamiko"],
        "Musebeya":   ["Gasura","Kizi","Mugera","Musebeya","Rwamiko"],
        "Musubi":     ["Gasura","Kizi","Mugera","Musubi","Rwamiko"],
        "Nkomane":    ["Gasura","Kizi","Mugera","Nkomane","Rwamiko"],
        "Tare":       ["Gasura","Kizi","Mugera","Rwamiko","Tare"],
        "Uwinkingi":  ["Gasura","Kizi","Mugera","Rwamiko","Uwinkingi"],
    },
    "Nyanza": {
        "Busasamana": ["Busasamana","Gasura","Kizi","Mugera","Rwamiko"],
        "Cyabakamyi": ["Cyabakamyi","Gasura","Kizi","Mugera","Rwamiko"],
        "Kibirizi":   ["Gasura","Kibirizi","Kizi","Mugera","Rwamiko"],
        "Kigoma":     ["Gasura","Kigoma","Kizi","Mugera","Rwamiko"],
        "Mukingo":    ["Gasura","Kizi","Mugera","Mukingo","Rwamiko"],
        "Muyira":     ["Gasura","Kizi","Mugera","Muyira","Rwamiko"],
        "Ntyazo":     ["Gasura","Kizi","Mugera","Ntyazo","Rwamiko"],
        "Nyagisozi":  ["Gasura","Kizi","Mugera","Nyagisozi","Rwamiko"],
        "Rwabicuma":  ["Gasura","Kizi","Mugera","Rwabicuma","Rwamiko"],
    },
    "Nyaruguru": {
        "Busanze":   ["Busanze","Gasura","Kizi","Mugera","Rwamiko"],
        "Cyahinda":  ["Cyahinda","Gasura","Kizi","Mugera","Rwamiko"],
        "Kibeho":    ["Gasura","Kibeho","Kizi","Mugera","Rwamiko"],
        "Kivu":      ["Gasura","Kivu","Kizi","Mugera","Rwamiko"],
        "Mata":      ["Gasura","Kizi","Mata","Mugera","Rwamiko"],
        "Muganza":   ["Gasura","Kizi","Muganza","Mugera","Rwamiko"],
        "Munini":    ["Gasura","Kizi","Mugera","Munini","Rwamiko"],
        "Ngera":     ["Gasura","Kizi","Mugera","Ngera","Rwamiko"],
        "Ngoma":     ["Gasura","Kizi","Mugera","Ngoma","Rwamiko"],
        "Nyabimata": ["Gasura","Kizi","Mugera","Nyabimata","Rwamiko"],
        "Nyagisozi": ["Gasura","Kizi","Mugera","Nyagisozi","Rwamiko"],
        "Ruheru":    ["Gasura","Kizi","Mugera","Ruheru","Rwamiko"],
        "Ruramba":   ["Gasura","Kizi","Mugera","Ruramba","Rwamiko"],
        "Rusenge":   ["Gasura","Kizi","Mugera","Rusenge","Rwamiko"],
    },
    "Ruhango": {
        "Bweramana": ["Bweramana","Gasura","Kizi","Mugera","Rwamiko"],
        "Byimana":   ["Byimana","Gasura","Kizi","Mugera","Rwamiko"],
        "Kabagali":  ["Gasura","Kabagali","Kizi","Mugera","Rwamiko"],
        "Kinazi":    ["Gasura","Kinazi","Kizi","Mugera","Rwamiko"],
        "Kinihira":  ["Gasura","Kinihira","Kizi","Mugera","Rwamiko"],
        "Mbuye":     ["Gasura","Kizi","Mbuye","Mugera","Rwamiko"],
        "Mwendo":    ["Gasura","Kizi","Mugera","Mwendo","Rwamiko"],
        "Ntongwe":   ["Gasura","Kizi","Mugera","Ntongwe","Rwamiko"],
        "Ruhango":   ["Gasura","Kizi","Mugera","Ruhango","Rwamiko"],
    },
    # ── Eastern Province ──────────────────────────────────────────────────────
    "Bugesera": {
        "Gashora":    ["Gasura","Gashora","Kizi","Mugera","Rwamiko"],
        "Juru":       ["Gasura","Juru","Kizi","Mugera","Rwamiko"],
        "Kamabuye":   ["Gasura","Kamabuye","Kizi","Mugera","Rwamiko"],
        "Ntarama":    ["Gasura","Kizi","Mugera","Ntarama","Rwamiko"],
        "Mareba":     ["Gasura","Kizi","Mareba","Mugera","Rwamiko"],
        "Mayange":    ["Gasura","Kizi","Mayange","Mugera","Rwamiko"],
        "Musenyi":    ["Gasura","Kizi","Mugera","Musenyi","Rwamiko"],
        "Mwogo":      ["Gasura","Kizi","Mugera","Mwogo","Rwamiko"],
        "Ngeruka":    ["Gasura","Kizi","Mugera","Ngeruka","Rwamiko"],
        "Nyamata":    ["Gasura","Kizi","Mugera","Nyamata","Rwamiko"],
        "Nyarugenge": ["Gasura","Kizi","Mugera","Nyarugenge","Rwamiko"],
        "Rilima":     ["Gasura","Kizi","Mugera","Rilima","Rwamiko"],
        "Ruhuha":     ["Gasura","Kizi","Mugera","Ruhuha","Rwamiko"],
        "Rweru":      ["Gasura","Kizi","Mugera","Rwamiko","Rweru"],
        "Shyara":     ["Gasura","Kizi","Mugera","Rwamiko","Shyara"],
    },
    "Gatsibo": {
        "Gasange":    ["Gasange","Gasura","Kizi","Mugera","Rwamiko"],
        "Gatsibo":    ["Gasura","Gatsibo","Kizi","Mugera","Rwamiko"],
        "Gitoki":     ["Gasura","Gitoki","Kizi","Mugera","Rwamiko"],
        "Kabarore":   ["Gasura","Kabarore","Kizi","Mugera","Rwamiko"],
        "Kageyo":     ["Gasura","Kageyo","Kizi","Mugera","Rwamiko"],
        "Kiramuruzi": ["Gasura","Kiramuruzi","Kizi","Mugera","Rwamiko"],
        "Kiziguro":   ["Gasura","Kiziguro","Kizi","Mugera","Rwamiko"],
        "Muhura":     ["Gasura","Kizi","Mugera","Muhura","Rwamiko"],
        "Murambi":    ["Gasura","Kizi","Mugera","Murambi","Rwamiko"],
        "Ngarama":    ["Gasura","Kizi","Mugera","Ngarama","Rwamiko"],
        "Nyagihanga": ["Gasura","Kizi","Mugera","Nyagihanga","Rwamiko"],
        "Remera":     ["Gasura","Kizi","Mugera","Remera","Rwamiko"],
        "Rugarama":   ["Gasura","Kizi","Mugera","Rugarama","Rwamiko"],
        "Rwimbogo":   ["Gasura","Kizi","Mugera","Rwamiko","Rwimbogo"],
    },
    "Kayonza": {
        "Gahini":     ["Gasura","Gahini","Kizi","Mugera","Rwamiko"],
        "Kabarondo":  ["Gasura","Kabarondo","Kizi","Mugera","Rwamiko"],
        "Mukarange":  ["Gasura","Kizi","Mugera","Mukarange","Rwamiko"],
        "Murama":     ["Gasura","Kizi","Mugera","Murama","Rwamiko"],
        "Murundi":    ["Gasura","Kizi","Mugera","Murundi","Rwamiko"],
        "Mwiri":      ["Gasura","Kizi","Mugera","Mwiri","Rwamiko"],
        "Ndego":      ["Gasura","Kizi","Mugera","Ndego","Rwamiko"],
        "Nyamirama":  ["Gasura","Kizi","Mugera","Nyamirama","Rwamiko"],
        "Rukara":     ["Gasura","Kizi","Mugera","Rukara","Rwamiko"],
        "Ruramira":   ["Gasura","Kizi","Mugera","Ruramira","Rwamiko"],
        "Rwinkwavu":  ["Gasura","Kizi","Mugera","Rwamiko","Rwinkwavu"],
    },
    "Kirehe": {
        "Gahara":    ["Gasura","Gahara","Kizi","Mugera","Rwamiko"],
        "Gatore":    ["Gasura","Gatore","Kizi","Mugera","Rwamiko"],
        "Kigarama":  ["Gasura","Kigarama","Kizi","Mugera","Rwamiko"],
        "Kigina":    ["Gasura","Kigina","Kizi","Mugera","Rwamiko"],
        "Kirehe":    ["Gasura","Kirehe","Kizi","Mugera","Rwamiko"],
        "Mahama":    ["Gasura","Kizi","Mahama","Mugera","Rwamiko"],
        "Mpanga":    ["Gasura","Kizi","Mpanga","Mugera","Rwamiko"],
        "Musaza":    ["Gasura","Kizi","Mugera","Musaza","Rwamiko"],
        "Mushikiri": ["Gasura","Kizi","Mugera","Mushikiri","Rwamiko"],
        "Nasho":     ["Gasura","Kizi","Mugera","Nasho","Rwamiko"],
        "Nyamugari": ["Gasura","Kizi","Mugera","Nyamugari","Rwamiko"],
        "Nyarubuye": ["Gasura","Kizi","Mugera","Nyarubuye","Rwamiko"],
    },
    "Ngoma": {
        "Gashanda":  ["Gasura","Gashanda","Kizi","Mugera","Rwamiko"],
        "Jarama":    ["Gasura","Jarama","Kizi","Mugera","Rwamiko"],
        "Karembo":   ["Gasura","Karembo","Kizi","Mugera","Rwamiko"],
        "Kazo":      ["Gasura","Kazo","Kizi","Mugera","Rwamiko"],
        "Kibungo":   ["Gasura","Kibungo","Kizi","Mugera","Rwamiko"],
        "Mugesera":  ["Gasura","Kizi","Mugera","Mugesera","Rwamiko"],
        "Murama":    ["Gasura","Kizi","Mugera","Murama","Rwamiko"],
        "Mutenderi": ["Gasura","Kizi","Mugera","Mutenderi","Rwamiko"],
        "Remera":    ["Gasura","Kizi","Mugera","Remera","Rwamiko"],
        "Rukira":    ["Gasura","Kizi","Mugera","Rukira","Rwamiko"],
        "Rukumberi": ["Gasura","Kizi","Mugera","Rukumberi","Rwamiko"],
        "Rurenge":   ["Gasura","Kizi","Mugera","Rurenge","Rwamiko"],
        "Sake":      ["Gasura","Kizi","Mugera","Rwamiko","Sake"],
        "Zaza":      ["Gasura","Kizi","Mugera","Rwamiko","Zaza"],
    },
    "Nyagatare": {
        "Gatunda":    ["Gasura","Gatunda","Kizi","Mugera","Rwamiko"],
        "Karama":     ["Gasura","Karama","Kizi","Mugera","Rwamiko"],
        "Karangazi":  ["Gasura","Karangazi","Kizi","Mugera","Rwamiko"],
        "Katabagemu": ["Gasura","Katabagemu","Kizi","Mugera","Rwamiko"],
        "Kiyombe":    ["Gasura","Kiyombe","Kizi","Mugera","Rwamiko"],
        "Matimba":    ["Gasura","Kizi","Matimba","Mugera","Rwamiko"],
        "Mimuli":     ["Gasura","Kizi","Mimuli","Mugera","Rwamiko"],
        "Mukama":     ["Gasura","Kizi","Mugera","Mukama","Rwamiko"],
        "Musheli":    ["Gasura","Kizi","Mugera","Musheli","Rwamiko"],
        "Nyagatare":  ["Gasura","Kizi","Mugera","Nyagatare","Rwamiko"],
        "Rukomo":     ["Gasura","Kizi","Mugera","Rukomo","Rwamiko"],
        "Rwempasha":  ["Gasura","Kizi","Mugera","Rwamiko","Rwempasha"],
        "Rwimiyaga":  ["Gasura","Kizi","Mugera","Rwamiko","Rwimiyaga"],
        "Tabagwe":    ["Gasura","Kizi","Mugera","Rwamiko","Tabagwe"],
    },
    "Rwamagana": {
        "Fumbwe":     ["Fumbwe","Gasura","Kizi","Mugera","Rwamiko"],
        "Gahengeri":  ["Gasura","Gahengeri","Kizi","Mugera","Rwamiko"],
        "Gishali":    ["Gasura","Gishali","Kizi","Mugera","Rwamiko"],
        "Karenge":    ["Gasura","Karenge","Kizi","Mugera","Rwamiko"],
        "Kigabiro":   ["Gasura","Kigabiro","Kizi","Mugera","Rwamiko"],
        "Muhazi":     ["Gasura","Kizi","Mugera","Muhazi","Rwamiko"],
        "Munyaga":    ["Gasura","Kizi","Mugera","Munyaga","Rwamiko"],
        "Munyiginya": ["Gasura","Kizi","Mugera","Munyiginya","Rwamiko"],
        "Musha":      ["Gasura","Kizi","Mugera","Musha","Rwamiko"],
        "Muyumbu":    ["Gasura","Kizi","Mugera","Muyumbu","Rwamiko"],
        "Mwulire":    ["Gasura","Kizi","Mugera","Mwulire","Rwamiko"],
        "Nyakariro":  ["Gasura","Kizi","Mugera","Nyakariro","Rwamiko"],
        "Nzige":      ["Gasura","Kizi","Mugera","Nzige","Rwamiko"],
        "Rubona":     ["Gasura","Kizi","Mugera","Rubona","Rwamiko"],
    },
    # ── Western Province ──────────────────────────────────────────────────────
    "Karongi": {
        "Bwishyura": ["Bwishyura","Gasura","Kizi","Mugera","Rwamiko"],
        "Gashari":   ["Gashari","Gasura","Kizi","Mugera","Rwamiko"],
        "Gishyita":  ["Gasura","Gishyita","Kizi","Mugera","Rwamiko"],
        "Gitesi":    ["Gasura","Gitesi","Kizi","Mugera","Rwamiko"],
        "Mubuga":    ["Gasura","Kizi","Mubuga","Mugera","Rwamiko"],
        "Murambi":   ["Gasura","Kizi","Mugera","Murambi","Rwamiko"],
        "Murundi":   ["Gasura","Kizi","Mugera","Murundi","Rwamiko"],
        "Mutuntu":   ["Gasura","Kizi","Mugera","Mutuntu","Rwamiko"],
        "Rugabano":  ["Gasura","Kizi","Mugera","Rugabano","Rwamiko"],
        "Ruganda":   ["Gasura","Kizi","Mugera","Ruganda","Rwamiko"],
        "Rwankuba":  ["Gasura","Kizi","Mugera","Rwamiko","Rwankuba"],
        "Twumba":    ["Gasura","Kizi","Mugera","Rwamiko","Twumba"],
    },
    "Ngororero": {
        "Bwira":     ["Bwira","Gasura","Kizi","Mugera","Rwamiko"],
        "Gatumba":   ["Gasura","Gatumba","Kizi","Mugera","Rwamiko"],
        "Hindiro":   ["Gasura","Hindiro","Kizi","Mugera","Rwamiko"],
        "Kabaya":    ["Gasura","Kabaya","Kizi","Mugera","Rwamiko"],
        "Kageyo":    ["Gasura","Kageyo","Kizi","Mugera","Rwamiko"],
        "Kavumu":    ["Gasura","Kavumu","Kizi","Mugera","Rwamiko"],
        "Matyazo":   ["Gasura","Kizi","Matyazo","Mugera","Rwamiko"],
        "Muhanda":   ["Gasura","Kizi","Mugera","Muhanda","Rwamiko"],
        "Muhororo":  ["Gasura","Kizi","Mugera","Muhororo","Rwamiko"],
        "Ndaro":     ["Gasura","Kizi","Mugera","Ndaro","Rwamiko"],
        "Ngororero": ["Gasura","Kizi","Mugera","Ngororero","Rwamiko"],
        "Nyange":    ["Gasura","Kizi","Mugera","Nyange","Rwamiko"],
        "Sovu":      ["Gasura","Kizi","Mugera","Rwamiko","Sovu"],
    },
    "Nyabihu": {
        "Bigogwe":  ["Bigogwe","Gasura","Kizi","Mugera","Rwamiko"],
        "Jomba":    ["Gasura","Jomba","Kizi","Mugera","Rwamiko"],
        "Kabatwa":  ["Gasura","Kabatwa","Kizi","Mugera","Rwamiko"],
        "Karago":   ["Gasura","Karago","Kizi","Mugera","Rwamiko"],
        "Kintobo":  ["Gasura","Kintobo","Kizi","Mugera","Rwamiko"],
        "Mukamira": ["Gasura","Kizi","Mugera","Mukamira","Rwamiko"],
        "Muringa":  ["Gasura","Kizi","Mugera","Muringa","Rwamiko"],
        "Rambura":  ["Gasura","Kizi","Mugera","Rambura","Rwamiko"],
        "Rugera":   ["Gasura","Kizi","Mugera","Rugera","Rwamiko"],
        "Rurembo":  ["Gasura","Kizi","Mugera","Rurembo","Rwamiko"],
        "Shyira":   ["Gasura","Kizi","Mugera","Rwamiko","Shyira"],
    },
    "Nyamasheke": {
        "Bushekeri":    ["Bushekeri","Gasura","Kizi","Mugera","Rwamiko"],
        "Bushenge":     ["Bushenge","Gasura","Kizi","Mugera","Rwamiko"],
        "Cyato":        ["Cyato","Gasura","Kizi","Mugera","Rwamiko"],
        "Gihombo":      ["Gasura","Gihombo","Kizi","Mugera","Rwamiko"],
        "Kagano":       ["Gasura","Kagano","Kizi","Mugera","Rwamiko"],
        "Kanjongo":     ["Gasura","Kanjongo","Kizi","Mugera","Rwamiko"],
        "Karambi":      ["Gasura","Karambi","Kizi","Mugera","Rwamiko"],
        "Karengera":    ["Gasura","Karengera","Kizi","Mugera","Rwamiko"],
        "Kirimbi":      ["Gasura","Kirimbi","Kizi","Mugera","Rwamiko"],
        "Macuba":       ["Gasura","Kizi","Macuba","Mugera","Rwamiko"],
        "Mahembe":      ["Gasura","Kizi","Mahembe","Mugera","Rwamiko"],
        "Nyabitekeri":  ["Gasura","Kizi","Mugera","Nyabitekeri","Rwamiko"],
        "Rangiro":      ["Gasura","Kizi","Mugera","Rangiro","Rwamiko"],
        "Ruharambuga":  ["Gasura","Kizi","Mugera","Ruharambuga","Rwamiko"],
        "Shangi":       ["Gasura","Kizi","Mugera","Rwamiko","Shangi"],
    },
    "Rubavu": {
        "Bugeshi":    ["Bugeshi","Gasura","Kizi","Mugera","Rwamiko"],
        "Busasamana": ["Busasamana","Gasura","Kizi","Mugera","Rwamiko"],
        "Cyanzarwe":  ["Cyanzarwe","Gasura","Kizi","Mugera","Rwamiko"],
        "Gisenyi":    ["Gasura","Gisenyi","Kizi","Mugera","Rwamiko"],
        "Kanama":     ["Gasura","Kanama","Kizi","Mugera","Rwamiko"],
        "Kanzenze":   ["Gasura","Kanzenze","Kizi","Mugera","Rwamiko"],
        "Mudende":    ["Gasura","Kizi","Mudende","Mugera","Rwamiko"],
        "Nyakiliba":  ["Gasura","Kizi","Mugera","Nyakiliba","Rwamiko"],
        "Nyamyumba":  ["Gasura","Kizi","Mugera","Nyamyumba","Rwamiko"],
        "Nyundo":     ["Gasura","Kizi","Mugera","Nyundo","Rwamiko"],
        "Rugerero":   ["Gasura","Kizi","Mugera","Rugerero","Rwamiko"],
    },
    "Rusizi": {
        "Bugarama":      ["Bugarama","Gasura","Kizi","Mugera","Rwamiko"],
        "Bweyeye":       ["Bweyeye","Gasura","Kizi","Mugera","Rwamiko"],
        "Giheke":        ["Gasura","Giheke","Kizi","Mugera","Rwamiko"],
        "Gihundwe":      ["Gasura","Gihundwe","Kizi","Mugera","Rwamiko"],
        "Gikundamvura":  ["Gasura","Gikundamvura","Kizi","Mugera","Rwamiko"],
        "Gitambi":       ["Gasura","Gitambi","Kizi","Mugera","Rwamiko"],
        "Kamembe":       ["Gasura","Kamembe","Kizi","Mugera","Rwamiko"],
        "Muganza":       ["Gasura","Kizi","Muganza","Mugera","Rwamiko"],
        "Mururu":        ["Gasura","Kizi","Mugera","Mururu","Rwamiko"],
        "Nkungu":        ["Gasura","Kizi","Mugera","Nkungu","Rwamiko"],
        "Nyakabuye":     ["Gasura","Kizi","Mugera","Nyakabuye","Rwamiko"],
        "Nyandungu":     ["Gasura","Kizi","Mugera","Nyandungu","Rwamiko"],
        "Nzahaha":       ["Gasura","Kizi","Mugera","Nzahaha","Rwamiko"],
        "Nzovwe":        ["Gasura","Kizi","Mugera","Nzovwe","Rwamiko"],
        "Rwimbogo":      ["Gasura","Kizi","Mugera","Rwamiko","Rwimbogo"],
    },
    "Rutsiro": {
        "Boneza":    ["Boneza","Gasura","Kizi","Mugera","Rwamiko"],
        "Gihango":   ["Gasura","Gihango","Kizi","Mugera","Rwamiko"],
        "Kigeyo":    ["Gasura","Kigeyo","Kizi","Mugera","Rwamiko"],
        "Kivumu":    ["Gasura","Kivumu","Kizi","Mugera","Rwamiko"],
        "Manihira":  ["Gasura","Kizi","Manihira","Mugera","Rwamiko"],
        "Mukura":    ["Gasura","Kizi","Mugera","Mukura","Rwamiko"],
        "Murunda":   ["Gasura","Kizi","Mugera","Murunda","Rwamiko"],
        "Musasa":    ["Gasura","Kizi","Mugera","Musasa","Rwamiko"],
        "Mushonyi":  ["Gasura","Kizi","Mugera","Mushonyi","Rwamiko"],
        "Mushubati": ["Gasura","Kizi","Mugera","Mushubati","Rwamiko"],
        "Nyabirasi": ["Gasura","Kizi","Mugera","Nyabirasi","Rwamiko"],
        "Ruhango":   ["Gasura","Kizi","Mugera","Ruhango","Rwamiko"],
        "Rusebeya":  ["Gasura","Kizi","Mugera","Rusebeya","Rwamiko"],
    },
}

# Convenience: sectors listed per district (derived from _RW)
def _sectors_for(district: str) -> list[str]:
    return list(_RW.get(district, {}).keys())

def _cells_for(district: str, sector: str) -> list[str]:
    return _RW.get(district, {}).get(sector, [])

# Villages per cell — explicit for Kigali City; all others get synthetic fallback
_VIL: dict[str, dict[str, dict[str, list[str]]]] = {
    "Gasabo": {
        "Bumbogo":    {"Bidudu":    ["Bidudu","Kiramuruzi","Murambi","Nyabugogo","Taba"],
                       "Cyarubare": ["Bwampanga","Cyarubare","Gasaka","Kabuga","Rwintare"],
                       "Gasagara":  ["Gakenke","Gasagara","Gitega","Kamonyi","Mugina"],
                       "Kagugu":    ["Butare","Bwira","Kagugu","Karama","Mugina"],
                       "Ntarama":   ["Bugesera","Gitaraga","Kagugu","Ntarama","Ruhuha"],
                       "Rubaya":    ["Cyabakamyi","Kaguru","Nyamata","Rubaya","Ruhuha"]},
        "Gatsata":    {"Bibare":    ["Bibare","Gakwege","Kibungo","Rubirizi","Rugendabari"],
                       "Gisanga":   ["Gasare","Gisanga","Kagugu","Munini","Nyagatovu"],
                       "Gitega":    ["Gitega","Kabuye","Murambi","Nyundo","Rebero"],
                       "Kagugu":    ["Byimana","Gikondo","Kagugu","Rugarama","Rutonde"],
                       "Murundo":   ["Gasagara","Mugunga","Murundo","Nyakabanda","Rugina"],
                       "Ntarama":   ["Bugesera","Karama","Kibungo","Ntarama","Rwintare"]},
        "Gikomero":   {"Birunga":   ["Birunga","Kabeza","Kabuye","Murambi","Nyagahama"],
                       "Burega":    ["Burega","Gashike","Kabuye","Murambi","Rwintare"],
                       "Gacurabwenge": ["Gacurabwenge","Kagugu","Mugina","Murambi","Rutonde"],
                       "Gikomero":  ["Gikomero","Kagugu","Murambi","Nyagahama","Rubaya"],
                       "Kabuye":    ["Bugesera","Kabuye","Murambi","Nyundo","Ruhuha"],
                       "Kagina":    ["Byimana","Kagina","Karama","Rugarama","Rutonde"]},
        "Gisozi":     {"Bidudu":    ["Bidudu","Gako","Murama","Nyagahama","Taba"],
                       "Gasagara":  ["Gasagara","Gitega","Kagugu","Mugina","Rusororo"],
                       "Gisozi":    ["Bugesera","Gisozi","Kabeza","Murambi","Rutonde"],
                       "Murambi":   ["Bwira","Murambi","Nyabugogo","Rebero","Rubirizi"],
                       "Rugenge":   ["Kagugu","Karama","Rugenge","Rugarama","Rwintare"],
                       "Rusororo":  ["Birunga","Kabuye","Mugina","Rusororo","Taba"]},
        "Jabana":     {"Bwiza":     ["Bwiza","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gasagara":  ["Gasagara","Gitega","Kagugu","Mugina","Rugarama"],
                       "Jabana":    ["Jabana","Karama","Murambi","Nyagahama","Rusororo"],
                       "Karuruma":  ["Byimana","Kagugu","Karuruma","Murambi","Rebero"],
                       "Mburabuturo": ["Bugesera","Kagugu","Mburabuturo","Murambi","Ruhuha"],
                       "Nyagatovu": ["Kabuye","Mugina","Nyagatovu","Rubaya","Rwintare"]},
        "Jali":       {"Bukirwa":   ["Bukirwa","Gako","Kagugu","Murambi","Taba"],
                       "Gasharu":   ["Gasharu","Gitega","Kabuye","Mugina","Rutonde"],
                       "Jali":      ["Byimana","Jali","Kagugu","Murambi","Rusororo"],
                       "Kabuga":    ["Gakwege","Kabuga","Karama","Murambi","Rubaya"],
                       "Rubungo":   ["Birunga","Kagugu","Murambi","Rubungo","Rwintare"],
                       "Rutonde":   ["Bugesera","Kagugu","Nyagahama","Ruhuha","Rutonde"]},
        "Kacyiru":    {"Kamatamu":  ["Kamatamu","Karama","Murambi","Nyundo","Rubaya"],
                       "Kacyiru":   ["Gakwege","Kacyiru","Murambi","Rebero","Rugarama"],
                       "Kamutwa":   ["Bwira","Kamutwa","Murambi","Nyabugogo","Rutonde"],
                       "Kibagabaga": ["Byimana","Kagugu","Kibagabaga","Murambi","Rusororo"],
                       "Nyarutarama": ["Gisozi","Murambi","Nyarutarama","Rebero","Rwintare"]},
        "Kimihurura": {"Gikondo":   ["Gakwege","Gikondo","Kagugu","Murambi","Rubaya"],
                       "Kagugu":    ["Kagugu","Karama","Murambi","Nyabugogo","Rutonde"],
                       "Kimihurura": ["Bwira","Kabuye","Kimihurura","Rebero","Rugarama"],
                       "Rugando":   ["Byimana","Kagugu","Murambi","Rugando","Rwintare"]},
        "Kimironko":  {"Bibare":    ["Bibare","Gakwege","Kagugu","Murambi","Nyagahama"],
                       "Kanzenze":  ["Gakwege","Kagugu","Kanzenze","Murambi","Rubaya"],
                       "Kimironko": ["Byimana","Kagugu","Kimironko","Murambi","Rusororo"],
                       "Mageragere": ["Gisozi","Kagugu","Mageragere","Murambi","Rutonde"],
                       "Rukiri":    ["Birunga","Kagugu","Murambi","Rubungo","Rukiri"]},
        "Kinyinya":   {"Kabuyange":  ["Gakwege","Kabuyange","Karama","Murambi","Rutonde"],
                       "Kinyinya":   ["Birunga","Kagugu","Kinyinya","Murambi","Rwintare"],
                       "Murama":     ["Byimana","Kagugu","Murama","Murambi","Rubaya"],
                       "Nyirangarama": ["Bugesera","Kagugu","Murambi","Nyirangarama","Ruhuha"],
                       "Rukuri":     ["Gakwege","Kagugu","Murambi","Rubungo","Rukuri"]},
        "Ndera":      {"Kagugu":    ["Gakwege","Kagugu","Murambi","Rugarama","Rutonde"],
                       "Musenyi":   ["Birunga","Kagugu","Murambi","Musenyi","Rwintare"],
                       "Ndera":     ["Byimana","Kabuye","Murambi","Ndera","Rusororo"],
                       "Rutonde":   ["Bugesera","Kagugu","Murambi","Rubaya","Rutonde"]},
        "Nduba":      {"Busenyi":   ["Busenyi","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kagugu":    ["Birunga","Kagugu","Murambi","Rugarama","Rwintare"],
                       "Nduba":     ["Byimana","Kabuye","Murambi","Nduba","Rusororo"],
                       "Rurimbi":   ["Bugesera","Kagugu","Murambi","Rubaya","Rurimbi"]},
        "Remera":     {"Gisimenti": ["Gakwege","Gisimenti","Kagugu","Murambi","Rutonde"],
                       "Nyabisindu": ["Birunga","Kagugu","Murambi","Nyabisindu","Rwintare"],
                       "Odesha":    ["Byimana","Kagugu","Murambi","Odesha","Rusororo"],
                       "Rukiri":    ["Bugesera","Kagugu","Murambi","Rubaya","Rukiri"]},
        "Rusororo":   {"Bumbogo":   ["Bumbogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gasagara":  ["Birunga","Gasagara","Kagugu","Murambi","Rwintare"],
                       "Karuruma":  ["Byimana","Kagugu","Karuruma","Murambi","Rusororo"],
                       "Ntarama":   ["Bugesera","Kagugu","Murambi","Ntarama","Ruhuha"],
                       "Rusororo":  ["Gakwege","Kagugu","Murambi","Rusororo","Taba"]},
        "Rutunga":    {"Bidudu":    ["Bidudu","Gakwege","Kagugu","Murambi","Taba"],
                       "Kagina":    ["Birunga","Kagina","Karama","Murambi","Rutonde"],
                       "Murambi":   ["Byimana","Kabuye","Murambi","Nyabugogo","Rusororo"],
                       "Rutunga":   ["Bugesera","Kagugu","Murambi","Rubaya","Rutunga"]},
    },
    "Kicukiro": {
        "Gahanga":    {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Cyimo":     ["Birunga","Cyimo","Kagugu","Murambi","Rwintare"],
                       "Gahanga":   ["Byimana","Gahanga","Kagugu","Murambi","Rusororo"],
                       "Kibirizi":  ["Bugesera","Kagugu","Kibirizi","Murambi","Ruhuha"],
                       "Ruhuha":    ["Gakwege","Kagugu","Murambi","Ruhuha","Taba"]},
        "Gatenga":    {"Gatenga":   ["Gatenga","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kabarondo": ["Birunga","Kagugu","Kabarondo","Murambi","Rwintare"],
                       "Kagugu":    ["Byimana","Kagugu","Murambi","Rugarama","Rusororo"],
                       "Kibirizi":  ["Bugesera","Kagugu","Kibirizi","Murambi","Ruhuha"],
                       "Nyabisindu": ["Gakwege","Kagugu","Murambi","Nyabisindu","Taba"]},
        "Gikondo":    {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gikondo":   ["Birunga","Gikondo","Kagugu","Murambi","Rwintare"],
                       "Kagugu":    ["Byimana","Kagugu","Murambi","Rugarama","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Kagarama":   {"Kagarama":  ["Gakwege","Kagugu","Kagarama","Murambi","Rutonde"],
                       "Kibagabaga": ["Birunga","Kagugu","Kibagabaga","Murambi","Rwintare"],
                       "Nyanza":    ["Byimana","Kagugu","Murambi","Nyanza","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Kanombe":    {"Gikondo":   ["Gakwege","Gikondo","Kagugu","Murambi","Rutonde"],
                       "Kanombe":   ["Birunga","Kagugu","Kanombe","Murambi","Rwintare"],
                       "Kibagabaga": ["Byimana","Kagugu","Kibagabaga","Murambi","Rusororo"],
                       "Nyarugunga": ["Bugesera","Kagugu","Murambi","Nyarugunga","Ruhuha"]},
        "Kicukiro":   {"Kicukiro":  ["Gakwege","Kagugu","Kicukiro","Murambi","Rutonde"],
                       "Niboye":    ["Birunga","Kagugu","Murambi","Niboye","Rwintare"],
                       "Nyarugunga": ["Byimana","Kagugu","Murambi","Nyarugunga","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Masaka":     {"Kabuye":    ["Gakwege","Kagugu","Kabuye","Murambi","Rutonde"],
                       "Masaka":    ["Birunga","Kagugu","Masaka","Murambi","Rwintare"],
                       "Nzige":     ["Byimana","Kagugu","Murambi","Nzige","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Niboye":     {"Kibirizi":  ["Gakwege","Kagugu","Kibirizi","Murambi","Rutonde"],
                       "Niboye":    ["Birunga","Kagugu","Murambi","Niboye","Rwintare"],
                       "Ruhuha":    ["Byimana","Kagugu","Murambi","Ruhuha","Rusororo"],
                       "Rutunga":   ["Bugesera","Kagugu","Murambi","Ruhuha","Rutunga"]},
        "Nyarugunga": {"Kadahokwa": ["Gakwege","Kadahokwa","Kagugu","Murambi","Rutonde"],
                       "Nyarugunga": ["Birunga","Kagugu","Murambi","Nyarugunga","Rwintare"],
                       "Rugunga":   ["Byimana","Kagugu","Murambi","Rugunga","Rusororo"],
                       "Rusororo":  ["Bugesera","Kagugu","Murambi","Ruhuha","Rusororo"]},
        "Rubilizi":   {"Gikomero":  ["Gakwege","Gikomero","Kagugu","Murambi","Rutonde"],
                       "Nyarugenge": ["Birunga","Kagugu","Murambi","Nyarugenge","Rwintare"],
                       "Rubilizi":  ["Byimana","Kagugu","Murambi","Rubilizi","Rusororo"],
                       "Rusororo":  ["Bugesera","Kagugu","Murambi","Ruhuha","Rusororo"]},
    },
    "Nyarugenge": {
        "Gitega":     {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gitega":    ["Birunga","Gitega","Kagugu","Murambi","Rwintare"],
                       "Kagugu":    ["Byimana","Kagugu","Murambi","Rugarama","Rusororo"],
                       "Nyarutarama": ["Bugesera","Kagugu","Murambi","Nyarutarama","Ruhuha"]},
        "Kanyinya":   {"Bidudu":    ["Bidudu","Gakwege","Kagugu","Murambi","Taba"],
                       "Gikondo":   ["Birunga","Gikondo","Kagugu","Murambi","Rwintare"],
                       "Kanyinya":  ["Byimana","Kagugu","Kanyinya","Murambi","Rusororo"],
                       "Murambi":   ["Bugesera","Kagugu","Murambi","Nyabugogo","Ruhuha"]},
        "Kigali":     {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kigali":    ["Birunga","Kagugu","Kigali","Murambi","Rwintare"],
                       "Rugenge":   ["Byimana","Kagugu","Murambi","Rugenge","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Kimisagara": {"Kimisagara": ["Gakwege","Kagugu","Kimisagara","Murambi","Rutonde"],
                       "Muhima":    ["Birunga","Kagugu","Murambi","Muhima","Rwintare"],
                       "Nyabugogo": ["Byimana","Kagugu","Murambi","Nyabugogo","Rusororo"],
                       "Rugenge":   ["Bugesera","Kagugu","Murambi","Rugenge","Ruhuha"]},
        "Mageragere": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Mageragere": ["Birunga","Kagugu","Mageragere","Murambi","Rwintare"],
                       "Rugunga":   ["Byimana","Kagugu","Murambi","Rugunga","Rusororo"],
                       "Rusororo":  ["Bugesera","Kagugu","Murambi","Ruhuha","Rusororo"]},
        "Muhima":     {"Muhima":    ["Gakwege","Kagugu","Muhima","Murambi","Rutonde"],
                       "Nyamirambo": ["Birunga","Kagugu","Murambi","Nyamirambo","Rwintare"],
                       "Rugenge":   ["Byimana","Kagugu","Murambi","Rugenge","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Nyakabanda": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kibirizi":  ["Birunga","Kagugu","Kibirizi","Murambi","Rwintare"],
                       "Nyakabanda": ["Byimana","Kagugu","Murambi","Nyakabanda","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Nyamirambo": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Gikondo":   ["Birunga","Gikondo","Kagugu","Murambi","Rwintare"],
                       "Nyamirambo": ["Byimana","Kagugu","Murambi","Nyamirambo","Rusororo"],
                       "Rugunga":   ["Bugesera","Kagugu","Murambi","Rugunga","Ruhuha"]},
        "Nyarugenge": {"Kagugu":    ["Gakwege","Kagugu","Murambi","Rugarama","Rutonde"],
                       "Nyarugenge": ["Birunga","Kagugu","Murambi","Nyarugenge","Rwintare"],
                       "Rugenge":   ["Byimana","Kagugu","Murambi","Rugenge","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
        "Rwezamenyo": {"Biryogo":   ["Biryogo","Gakwege","Kagugu","Murambi","Rutonde"],
                       "Kagugu":    ["Birunga","Kagugu","Murambi","Rugarama","Rwintare"],
                       "Rugunga":   ["Byimana","Kagugu","Murambi","Rugunga","Rusororo"],
                       "Rwezamenyo": ["Bugesera","Kagugu","Murambi","Ruhuha","Rwezamenyo"]},
    },
}


def _villages_for(district: str, sector: str, cell: str) -> list[str]:
    """Return village list for a cell. Falls back to 4 synthetic names if not explicitly listed."""
    explicit = _VIL.get(district, {}).get(sector, {}).get(cell)
    if explicit:
        return explicit
    # Synthetic fallback ensures every cell has numbered village options
    return [f"{cell} I", f"{cell} II", f"{cell} III", f"{cell} IV"]

# ── Paginated USSD menu helpers ───────────────────────────────────────────────
_PAGE_SIZE = 7  # items per USSD screen (keeps responses under 182 chars)

def _paged_menu(header_en: str, header_rw: str, items: list[str],
                page: int, lang: str) -> str:
    """
    Build a paginated numbered list.
    Items on this page are numbered 1-7.
    If more pages exist: 8 = Next page →
    Always: 0 = Back
    """
    start = page * _PAGE_SIZE
    end   = min(start + _PAGE_SIZE, len(items))
    chunk = items[start:end]
    has_more = end < len(items)

    hdr  = header_en if lang == "en" else header_rw
    lines: list[str] = [hdr]
    for i, name in enumerate(chunk, 1):
        lines.append(f"{i}. {name}")
    if has_more:
        lines.append("8. More →" if lang == "en" else "8. Ibibukisho →")
    lines.append("0. Back" if lang == "en" else "0. Subira")
    return "CON " + "\n".join(lines)


def _resolve_paged(parts: list[str], start_idx: int,
                   items: list[str]) -> tuple[str | None, int, int]:
    """
    Walk parts from start_idx consuming page-navigation choices.
    Returns (selected_name | None, final_page, next_parts_idx).
    - selected_name is None if more input is needed (show menu)
    - selected_name is "" if user pressed 0 (back)
    """
    idx  = start_idx
    page = 0
    while idx < len(parts):
        choice = parts[idx]
        start  = page * _PAGE_SIZE
        end    = min(start + _PAGE_SIZE, len(items))
        chunk  = items[start:end]
        has_more = end < len(items)

        if choice == "0":
            return ("", page, idx + 1)   # back

        if choice == "8" and has_more:
            page += 1                     # next page
            idx  += 1
            continue

        try:
            sel = int(choice) - 1
            if 0 <= sel < len(chunk):
                return (chunk[sel], page, idx + 1)   # valid selection
        except ValueError:
            pass

        # invalid — re-show current page
        return (None, page, idx)

    # ran out of input — need one more step
    return (None, page, idx)

# ── Translations ──────────────────────────────────────────────────────────────

_T: dict[str, dict[str, str]] = {
    "welcome": {
        "en": (
            "CON Welcome to Temba Digital Bridge\n"
            "Murakaza neza - choose language:\n"
            "1. English\n"
            "2. Kinyarwanda"
        ),
        "rw": (
            "CON Welcome to Temba Digital Bridge\n"
            "Murakaza neza - hitamo ururimi:\n"
            "1. English\n"
            "2. Kinyarwanda"
        ),
    },
    "auth_menu": {
        "en": (
            "CON Temba Digital Bridge\n"
            "1. Register new account\n"
            "2. Login to my account\n"
            "0. Exit"
        ),
        "rw": (
            "CON Temba Digital Bridge\n"
            "1. Iyandikishe konti nshya\n"
            "2. Injira muri konti yanjye\n"
            "0. Kuva hano"
        ),
    },
    "not_registered_ussd": {
        "en": (
            "CON No account found for this number.\n"
            "1. Register now\n"
            "0. Back"
        ),
        "rw": (
            "CON Nta konti iboneka kuri uyu nomero.\n"
            "1. Iyandikishe ubu\n"
            "0. Subira"
        ),
    },
    "enter_name": {
        "en": "CON Enter your full name:",
        "rw": "CON Injiza amazina yawe yose:",
    },
    "select_province": {
        "en": (
            "CON Select your province:\n"
            "1. Kigali City\n"
            "2. Northern Province\n"
            "3. Southern Province\n"
            "4. Eastern Province\n"
            "5. Western Province\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo intara yawe:\n"
            "1. Umujyi wa Kigali\n"
            "2. Intara y'Amajyaruguru\n"
            "3. Intara y'Amajyepfo\n"
            "4. Intara y'Iburasirazuba\n"
            "5. Intara y'Iburengerazuba\n"
            "0. Subira"
        ),
    },
    "enter_sector": {
        "en": "CON Enter your sector name\n(or 0 to skip):",
        "rw": "CON Injiza umurenge wawe\n(cyangwa 0 kureka):",
    },
    "enter_cell": {
        "en": "CON Enter your cell name\n(or 0 to skip):",
        "rw": "CON Injiza akagari kawe\n(cyangwa 0 kureka):",
    },
    "enter_village": {
        "en": "CON Enter your village name\n(or 0 to skip):",
        "rw": "CON Injiza umudugudu wawe\n(cyangwa 0 kureka):",
    },
    "enter_sms_phone": {
        "en": (
            "CON Enter phone number to receive\n"
            "SMS tracking codes:\n"
            "(or 0 to use this number)"
        ),
        "rw": (
            "CON Injiza nomero ya telefoni\n"
            "kugira ngo ubone SMS z'ikurikirana:\n"
            "(cyangwa 0 gukoresha uyu nomero)"
        ),
    },
    "create_pin": {
        "en": "CON Create a 4-digit PIN\nfor your account:",
        "rw": "CON Kora PIN y'imibare 4\nkuri konti yawe:",
    },
    "confirm_pin": {
        "en": "CON Confirm your PIN:",
        "rw": "CON Emeza PIN yawe:",
    },
    "pin_mismatch": {
        "en": "END PINs do not match.\nDial again to retry.",
        "rw": "END PIN ntizihura.\nHamagara nanone ugerageze.",
    },
    "pin_invalid": {
        "en": "END PIN must be exactly 4 digits.\nDial again to retry.",
        "rw": "END PIN igomba kuba imibare 4.\nHamagara nanone ugerageze.",
    },
    "account_created": {
        "en": (
            "END Account created!\n"
            "Your location is saved so providers\n"
            "can reach you faster.\n"
            "Dial *384*36640# and Login."
        ),
        "rw": (
            "END Konti yakozwe!\n"
            "Aho ubarizwa bwabitswe kugira\n"
            "amatangazo yoherezwa vuba.\n"
            "Hamagara *384*36640# uhitemo Injira."
        ),
    },
    "enter_pin": {
        "en": "CON Enter your 4-digit PIN:",
        "rw": "CON Injiza PIN yawe y'imibare 4:",
    },
    "setup_pin": {
        "en": (
            "CON Welcome! Create your\n"
            "4-digit USSD PIN:"
        ),
        "rw": (
            "CON Murakaza neza! Shyiraho\n"
            "PIN yawe y'imibare 4:"
        ),
    },
    "pin_set": {
        "en": "END PIN created! Dial again and choose Login to use services.",
        "rw": "END PIN yashyizweho! Hamagara nanone uhitemo Injira gukoresha serivisi.",
    },
    "wrong_pin": {
        "en": "END Wrong PIN. Dial again to retry.",
        "rw": "END PIN ntariyo. Hamagara nanone ugerageze.",
    },
    "main_menu": {
        "en": (
            "CON Temba Digital Bridge\n"
            "1. Report water issue\n"
            "2. Track my reports\n"
            "3. Book appointment\n"
            "4. My appointments\n"
            "5. Service request status\n"
            "6. Submit service request\n"
            "0. Exit"
        ),
        "rw": (
            "CON Temba Digital Bridge\n"
            "1. Tanga raporo y'amazi\n"
            "2. Gukurikirana raporo\n"
            "3. Gufata randevu\n"
            "4. Amadate yanjye\n"
            "5. Ibibazo by'ubusabire\n"
            "6. Saba serivisi\n"
            "0. Kuva hano"
        ),
    },
    "exit": {
        "en": "END Thank you for using Temba. Stay safe!",
        "rw": "END Murakoze gukoresha Temba. Mukomeze neza!",
    },
    "invalid": {
        "en": "CON Invalid choice. Try again.\n0. Back",
        "rw": "CON Amahitamo atariyo. Ongera ugerageze.\n0. Subira",
    },
    "no_providers": {
        "en": "END No water providers available.\nTry again later.",
        "rw": "END Nta batanga serivisi bahari.\nOngera ugerageze nyuma.",
    },
    # ── Report flow ───────────────────────────────────────────────────────────
    "report_cat": {
        "en": (
            "CON Select issue type:\n"
            "1. Contamination\n"
            "2. Pipe burst / leak\n"
            "3. No water supply\n"
            "4. Low pressure\n"
            "5. Other\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo ubwoko bw'ikibazo:\n"
            "1. Amazi yanduye\n"
            "2. Umuyoboro wabuze\n"
            "3. Nta mazi\n"
            "4. Ingufu nke\n"
            "5. Ibindi\n"
            "0. Subira"
        ),
    },
    "report_urgency": {
        "en": (
            "CON How urgent?\n"
            "1. High - health risk\n"
            "2. Medium - significant impact\n"
            "3. Low - minor issue\n"
            "0. Back"
        ),
        "rw": (
            "CON Byihutirwa kangahe?\n"
            "1. Byihutirwa cyane - akaga\n"
            "2. Hagati - ingaruka nini\n"
            "3. Bike - ikibazo gito\n"
            "0. Subira"
        ),
    },
    "report_confirm": {
        "en": (
            "CON Ready to submit:\n"
            "Issue: {cat}\n"
            "Urgency: {urgency}\n"
            "Provider: {provider}\n"
            "1. Confirm & submit\n"
            "0. Cancel"
        ),
        "rw": (
            "CON Raporo iri gutegurwa:\n"
            "Ikibazo: {cat}\n"
            "Byihutirwa: {urgency}\n"
            "Umutanga: {provider}\n"
            "1. Emeza no kohereza\n"
            "0. Kureka"
        ),
    },
    "report_submitted": {
        "en": "END Report submitted!\nTracking code:\n{ref}\nVisit temba.rw to track\nyour issue progress.",
        "rw": "END Raporo yoherejwe!\nCode yo gukurikirana:\n{ref}\nGura temba.rw urebe\naho ikibazo cyanyu kigeze.",
    },
    "no_reports": {
        "en": "END You have no reports yet.",
        "rw": "END Nta raporo ufite ubu.",
    },
    "track_header": {
        "en": "END Your recent reports:\n",
        "rw": "END Raporo zawe za vuba:\n",
    },
    # ── Appointment flow ──────────────────────────────────────────────────────
    "appt_provider_hdr": {
        "en": "CON Select water provider:\n",
        "rw": "CON Hitamo umutanga serivisi w'amazi:\n",
    },
    "appt_reason": {
        "en": (
            "CON Appointment reason:\n"
            "1. New connection\n"
            "2. Meter reading\n"
            "3. Pipe repair\n"
            "4. Consultation\n"
            "5. Inspection\n"
            "6. Billing\n"
            "7. Other\n"
            "0. Back"
        ),
        "rw": (
            "CON Impamvu ya randevu:\n"
            "1. Gutuza amazi mashya\n"
            "2. Gusoma igikangaza\n"
            "3. Gusana umuyoboro\n"
            "4. Inama\n"
            "5. Kugenzura\n"
            "6. Akamaro\n"
            "7. Ibindi\n"
            "0. Subira"
        ),
    },
    "appt_date_hdr": {
        "en": "CON Select appointment date:\n",
        "rw": "CON Hitamo itariki ya randevu:\n",
    },
    "appt_time": {
        "en": (
            "CON Select preferred time:\n"
            "1. 08:00 - 09:00\n"
            "2. 10:00 - 11:00\n"
            "3. 12:00 - 13:00\n"
            "4. 14:00 - 15:00\n"
            "5. 16:00 - 17:00\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo igihe:\n"
            "1. 08:00 - 09:00\n"
            "2. 10:00 - 11:00\n"
            "3. 12:00 - 13:00\n"
            "4. 14:00 - 15:00\n"
            "5. 16:00 - 17:00\n"
            "0. Subira"
        ),
    },
    "appt_confirm": {
        "en": (
            "CON Appointment summary:\n"
            "Provider: {provider}\n"
            "Date: {date}\n"
            "Time: {time}\n"
            "1. Confirm\n"
            "0. Cancel"
        ),
        "rw": (
            "CON Incamake ya randevu:\n"
            "Umutanga: {provider}\n"
            "Itariki: {date}\n"
            "Igihe: {time}\n"
            "1. Emeza\n"
            "0. Kureka"
        ),
    },
    "appt_submitted": {
        "en": "END Appointment requested!\nTracking code:\n{ref}\nVisit temba.rw to track\nyour appointment status.",
        "rw": "END Randevu yasabwe!\nCode yo gukurikirana:\n{ref}\nGura temba.rw urebe\naho randevu yawe igeze.",
    },
    # ── Service request flow ──────────────────────────────────────────────────
    "svc_type": {
        "en": (
            "CON Select service type:\n"
            "1. New water connection\n"
            "2. Water tank delivery\n"
            "3. Water truck delivery\n"
            "4. Meter support\n"
            "5. Technical inspection\n"
            "0. Back"
        ),
        "rw": (
            "CON Hitamo ubwoko bwa serivisi:\n"
            "1. Gutuza amazi mashya\n"
            "2. Gutanga tanki y'amazi\n"
            "3. Gutanga imodoka y'amazi\n"
            "4. Gufasha ku gikangaza\n"
            "5. Kugenzura imiyoboro\n"
            "0. Subira"
        ),
    },
    "svc_urgency": {
        "en": (
            "CON Urgency level:\n"
            "1. High - urgent\n"
            "2. Medium\n"
            "3. Low\n"
            "0. Back"
        ),
        "rw": (
            "CON Urwego rwo kubyihutira:\n"
            "1. Byihutirwa\n"
            "2. Hagati\n"
            "3. Bike\n"
            "0. Subira"
        ),
    },
    "svc_confirm": {
        "en": (
            "CON Service request:\n"
            "Service: {svc}\n"
            "Urgency: {urgency}\n"
            "Provider: {provider}\n"
            "1. Submit\n"
            "0. Cancel"
        ),
        "rw": (
            "CON Icyifuzo cya serivisi:\n"
            "Serivisi: {svc}\n"
            "Byihutirwa: {urgency}\n"
            "Umutanga: {provider}\n"
            "1. Ohereza\n"
            "0. Kureka"
        ),
    },
    "svc_submitted": {
        "en": "END Service request submitted!\nTracking code:\n{ref}\nVisit temba.rw to track\nyour request progress.",
        "rw": "END Icyifuzo cyoherejwe!\nCode yo gukurikirana:\n{ref}\nGura temba.rw urebe\naho icyifuzo cyanyu kigeze.",
    },
    "no_svc": {
        "en": "END You have no service requests yet.",
        "rw": "END Nta cyifuzo ufite ubu.",
    },
    "svc_track_header": {
        "en": "END Your recent service requests:\n",
        "rw": "END Ibirego byawe by'ubusabire:\n",
    },
    "no_appts": {
        "en": "END You have no appointments yet.\nDial *384*36640# to book one.",
        "rw": "END Nta randevu ufite ubu.\nHamagara *384*36640# gufata imwe.",
    },
    "appt_track_header": {
        "en": "END Your recent appointments:\n",
        "rw": "END Amadate yawe ya vuba:\n",
    },
}

# ── Lookup tables ─────────────────────────────────────────────────────────────

_CAT_MAP: dict[str, ReportCategory] = {
    "1": ReportCategory.CONTAMINATION,
    "2": ReportCategory.PIPE_BURST,
    "3": ReportCategory.NO_SUPPLY,
    "4": ReportCategory.LOW_PRESSURE,
    "5": ReportCategory.OTHER,
}
_CAT_EN  = {"1": "Contamination", "2": "Pipe burst", "3": "No supply", "4": "Low pressure", "5": "Other"}
_CAT_RW  = {"1": "Amazi yanduye", "2": "Umuyoboro wabuze", "3": "Nta mazi", "4": "Ingufu nke", "5": "Ibindi"}

_URG_MAP: dict[str, ReportUrgency] = {
    "1": ReportUrgency.HIGH,
    "2": ReportUrgency.MEDIUM,
    "3": ReportUrgency.LOW,
}
_URG_EN = {"1": "High", "2": "Medium", "3": "Low"}
_URG_RW = {"1": "Byihutirwa cyane", "2": "Hagati", "3": "Bike"}

_REASON_MAP: dict[str, AppointmentReason] = {
    "1": AppointmentReason.WATER_CONNECTION,
    "2": AppointmentReason.METER_READING,
    "3": AppointmentReason.PIPE_REPAIR,
    "4": AppointmentReason.CONSULTATION,
    "5": AppointmentReason.INSPECTION,
    "6": AppointmentReason.BILLING,
    "7": AppointmentReason.OTHER,
}

_TIME_SLOTS: dict[str, str] = {
    "1": "08:00",
    "2": "10:00",
    "3": "12:00",
    "4": "14:00",
    "5": "16:00",
}

_SVC_MAP: dict[str, ServiceRequestType] = {
    "1": ServiceRequestType.WATER_CONNECTION,
    "2": ServiceRequestType.TANK_DELIVERY,
    "3": ServiceRequestType.TRUCK_DELIVERY,
    "4": ServiceRequestType.METER_SUPPORT,
    "5": ServiceRequestType.INSPECTION,
}
_SVC_EN = {"1": "New connection", "2": "Tank delivery", "3": "Water truck", "4": "Meter support", "5": "Inspection"}
_SVC_RW = {"1": "Gutuza amazi", "2": "Tanki y'amazi", "3": "Imodoka y'amazi", "4": "Gikangaza", "5": "Kugenzura"}

_SVC_URG_MAP: dict[str, ServiceRequestUrgency] = {
    "1": ServiceRequestUrgency.HIGH,
    "2": ServiceRequestUrgency.MEDIUM,
    "3": ServiceRequestUrgency.LOW,
}
_SVC_URG_EN = {"1": "High", "2": "Medium", "3": "Low"}
_SVC_URG_RW = {"1": "Byihutirwa", "2": "Hagati", "3": "Bike"}

_APPT_REASON_EN: dict[str, str] = {
    "water_connection": "New connection", "meter_reading": "Meter reading",
    "pipe_repair": "Pipe repair", "consultation": "Consultation",
    "inspection": "Inspection", "billing": "Billing", "other": "Other",
}
_APPT_REASON_RW: dict[str, str] = {
    "water_connection": "Gutuza amazi", "meter_reading": "Gusoma igikangaza",
    "pipe_repair": "Gusana umuyoboro", "consultation": "Inama",
    "inspection": "Kugenzura", "billing": "Akamaro", "other": "Ibindi",
}

_STATUS_EN: dict[str, str] = {
    "open": "Open", "under_review": "Under Review", "in_progress": "In Progress",
    "resolved": "Resolved", "closed": "Closed",
    "submitted": "Submitted", "reviewing": "Reviewing", "approved": "Approved",
    "rejected": "Rejected", "completed": "Completed", "cancelled": "Cancelled",
    "pending": "Pending",
}
_STATUS_RW: dict[str, str] = {
    "open": "Ifunguye", "under_review": "Irasuzumwa", "in_progress": "Irakozwa",
    "resolved": "Yakemuwe", "closed": "Yafunzwe",
    "submitted": "Yoherejwe", "reviewing": "Irasuzumwa", "approved": "Yemejwe",
    "rejected": "Yanzwe", "completed": "Yarangiye", "cancelled": "Ivanwaho",
    "pending": "Itegereje",
}

# ── Internal helpers ──────────────────────────────────────────────────────────


def _t(key: str, lang: str, **kw: str) -> str:
    tmpl = _T.get(key, {}).get(lang) or _T.get(key, {}).get("en", "")
    return tmpl.format(**kw) if kw else tmpl


def _back(lang: str) -> str:
    return "0. Back" if lang == "en" else "0. Subira"


def _date_menu(lang: str) -> str:
    header = _t("appt_date_hdr", lang)
    lines = []
    for i in range(1, 5):
        d = date.today() + timedelta(days=i)
        lines.append(f"{i}. {d.strftime('%a %d %b')}")
    return header + "\n".join(lines) + "\n" + _back(lang)


def _date_from_idx(choice: str) -> date:
    return date.today() + timedelta(days=int(choice))


def _district_menu(prov_choice: str, lang: str) -> str:
    districts = _DISTRICTS.get(prov_choice, [])
    lines = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(districts))
    header = "CON Select your district:\n" if lang == "en" else "CON Hitamo akarere kawe:\n"
    return header + lines + "\n" + _back(lang)


_SIGNUP_PER_PAGE = 7  # items shown per USSD page in registration menus


def _paged_selection(
    parts: list[str], start_idx: int, items: list[str]
) -> tuple[str | None, int, int]:
    """Walk parts starting at start_idx consuming '9' (next-page) tokens.

    Returns (selected_name | 'BACK' | None, current_page, next_parts_idx).
    None means no selection yet — caller should show the appropriate page.
    """
    page = 0
    idx = start_idx
    while idx < len(parts):
        val = parts[idx]
        if val == "9":
            page += 1
            idx += 1
        elif val == "0":
            return "BACK", page, idx
        else:
            try:
                offset = page * _SIGNUP_PER_PAGE + int(val) - 1
                if 0 <= offset < len(items):
                    return items[offset], page, idx + 1
                # Invalid number on this page — re-show same page
            except ValueError:
                pass
            return None, page, idx
    return None, page, idx


def _sector_menu(district_name: str, lang: str, page: int) -> str:
    sectors = _sectors_for(district_name)
    start = page * _SIGNUP_PER_PAGE
    chunk = sectors[start: start + _SIGNUP_PER_PAGE]
    hdr = "CON Select your sector:\n" if lang == "en" else "CON Hitamo umurenge wawe:\n"
    lines = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(chunk))
    more = ("\n9. More >>" if lang == "en" else "\n9. Undi mwanya >>") if (start + _SIGNUP_PER_PAGE) < len(sectors) else ""
    return hdr + lines + more + "\n" + _back(lang)


def _cell_menu(district_name: str, sector_name: str, lang: str, page: int) -> str:
    cells = _cells_for(district_name, sector_name)
    start = page * _SIGNUP_PER_PAGE
    chunk = cells[start: start + _SIGNUP_PER_PAGE]
    hdr = "CON Select your cell:\n" if lang == "en" else "CON Hitamo akagari kawe:\n"
    lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(chunk))
    more = ("\n9. More >>" if lang == "en" else "\n9. Undi mwanya >>") if (start + _SIGNUP_PER_PAGE) < len(cells) else ""
    return hdr + lines + more + "\n" + _back(lang)


async def _fetch_providers(db: AsyncSession) -> list[Provider]:
    result = await db.execute(
        select(Provider)
        .where(Provider.status == ProviderStatus.APPROVED)
        .order_by(Provider.organization_name)
    )
    return list(result.scalars().all())


def _provider_menu(providers: list[Provider], lang: str) -> str:
    if not providers:
        return _t("no_providers", lang)
    header = _t("appt_provider_hdr", lang)
    lines = "\n".join(f"{i + 1}. {p.organization_name}" for i, p in enumerate(providers))
    return header + lines + "\n" + _back(lang)


def _pick_provider(providers: list[Provider], idx_str: str) -> Provider | None:
    try:
        return providers[int(idx_str) - 1]
    except (IndexError, ValueError):
        return None


def _short_id(obj_id: object) -> str:
    return str(obj_id)[:8].upper()


def _gen_ref(prefix: str) -> str:
    """Generate human-readable tracking code e.g. RPT-20260612-K7M3."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{date.today().strftime('%Y%m%d')}-{suffix}"


async def _sms(phone: str, message: str) -> None:
    """Send an SMS in a background thread so it never blocks the USSD response."""
    try:
        await asyncio.to_thread(send_sms_background, phone, message)
    except Exception:
        log.warning("ussd_sms_failed", phone=phone)


def _sms_phone(user: "User", calling_number: str) -> str:
    """Return the best phone to SMS: stored profile phone, else the calling number."""
    return user.phone or calling_number


# ── USSD callback ─────────────────────────────────────────────────────────────


@router.post("/callback", response_class=PlainTextResponse)
async def ussd_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(default=""),
) -> str:
    try:
        return await _handle_ussd(db, sessionId, phoneNumber, text)
    except Exception:
        log.exception("ussd_unhandled_error", session=sessionId, phone=phoneNumber, text=repr(text))
        return "END Service temporarily unavailable. Please try again in a moment."


async def _handle_ussd(
    db: AsyncSession, sessionId: str, phoneNumber: str, text: str
) -> str:
    parts = [p for p in text.split("*") if p]
    log.info("ussd_request", session=sessionId, phone=phoneNumber, text=repr(text))

    # ── Step 0: language selection ────────────────────────────────────────────
    if not parts:
        return _t("welcome", "en")

    lang_choice = parts[0]
    if lang_choice not in ("1", "2"):
        return _t("welcome", "en")
    lang = "en" if lang_choice == "1" else "rw"
    depth = len(parts)

    # ── Step 1: after language → Register / Login menu ────────────────────────
    if depth == 1:
        return _t("auth_menu", lang)

    route = parts[1]
    if route == "0":
        return _t("exit", lang)

    # ── REGISTER FLOW ─────────────────────────────────────────────────────────
    if route == "1":
        return await _signup_flow(parts, lang, phoneNumber, db)

    # ── LOGIN FLOW ────────────────────────────────────────────────────────────
    if route == "2":
        variants = _phone_variants(phoneNumber)
        result = await db.execute(
            select(User).where(or_(*[User.phone == v for v in variants]))
        )
        user: User | None = result.scalar_one_or_none()

        if user is None:
            # Not registered — bounce back to auth menu with message
            return _t("not_registered_ussd", lang)

        # Existing web user who has never set a USSD PIN → PIN setup
        if user.ussd_pin_hash is None:
            return await _pin_setup_flow(parts, user, lang, db)

        # parts[2] = PIN attempt
        if depth == 2:
            return _t("enter_pin", lang)

        pin_attempt = parts[2]
        if not verify_password(pin_attempt, user.ussd_pin_hash):
            return _t("wrong_pin", lang)

        # PIN valid → main menu or service
        if depth == 3:
            return _t("main_menu", lang)

        main = parts[3]
        if main == "0":
            return _t("exit", lang)

        # sub_parts = [main, sub1, sub2, ...] — normalized slice for _service_flow
        sub_parts = parts[3:]
        return await _service_flow(sub_parts, main, lang, user, db, phoneNumber)

    return _t("auth_menu", lang)


# ── Register flow ─────────────────────────────────────────────────────────────
# Registration parts layout (dynamic length due to pagination):
#   parts[0] = lang         ("1"=en, "2"=rw)
#   parts[1] = route        ("1" = register)
#   parts[2] = full name
#   parts[3] = province     (1-5)
#   parts[4] = district     (1-N)
#   parts[5..] = sector     one or more: "9" tokens (next-page) then a 1-7 selection
#   next..    = cell        same paged pattern
#   next+0    = 4-digit PIN
#   next+1    = confirm PIN

async def _signup_flow(
    parts: list[str], lang: str, phoneNumber: str, db: AsyncSession
) -> str:
    """
    7-step USSD registration capturing province, district, sector, and cell.
    Sector and cell menus are paginated (7 items + '9. More') so any-sized
    district fits within USSD character limits.
    """

    # Step 1: full name
    if len(parts) == 2:
        return _t("enter_name", lang)
    name = parts[2].strip()
    if not name:
        return _t("enter_name", lang)

    # Step 2: province (1-5)
    if len(parts) == 3:
        return _t("select_province", lang)
    prov_choice = parts[3]
    if prov_choice == "0":
        return _t("auth_menu", lang)
    try:
        prov_idx = int(prov_choice) - 1
        if not (0 <= prov_idx < len(_PROVINCES_LIST)):
            return _t("select_province", lang)
    except ValueError:
        return _t("select_province", lang)
    province_name = _PROVINCES_LIST[prov_idx]

    # Step 3: district
    if len(parts) == 4:
        return _district_menu(prov_choice, lang)
    dist_choice = parts[4]
    if dist_choice == "0":
        return _t("select_province", lang)
    districts = _DISTRICTS.get(prov_choice, [])
    try:
        dist_idx = int(dist_choice) - 1
        if not (0 <= dist_idx < len(districts)):
            return _district_menu(prov_choice, lang)
    except ValueError:
        return _district_menu(prov_choice, lang)
    district_name = districts[dist_idx]

    # Step 4: sector (paginated — starts at parts[5])
    sectors = _sectors_for(district_name)
    sector_name, sec_page, sec_next = _paged_selection(parts, 5, sectors)
    if sector_name is None:
        return _sector_menu(district_name, lang, sec_page)
    if sector_name == "BACK":
        return _district_menu(prov_choice, lang)

    # Step 5: cell (paginated — starts right after the sector selection)
    cells = _cells_for(district_name, sector_name)
    cell_name, cell_page, cell_next = _paged_selection(parts, sec_next, cells)
    if cell_name is None:
        return _cell_menu(district_name, sector_name, lang, cell_page)
    if cell_name == "BACK":
        return _sector_menu(district_name, lang, sec_page)

    # Step 6: create 4-digit PIN
    if len(parts) <= cell_next:
        return _t("create_pin", lang)
    pin = parts[cell_next]
    if len(pin) != 4 or not pin.isdigit():
        return _t("pin_invalid", lang)

    # Step 7: confirm PIN
    if len(parts) <= cell_next + 1:
        return _t("confirm_pin", lang)
    confirm = parts[cell_next + 1]
    if pin != confirm:
        return _t("pin_mismatch", lang)

    # ── Create the account ────────────────────────────────────────────────────
    safe_phone = re.sub(r"[\s\-]", "", phoneNumber)
    email_base = safe_phone.lstrip("+")
    email = f"{email_base}@ussd.temba.rw"

    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        existing.ussd_pin_hash = hash_password(pin)
        existing.province = province_name
        existing.district = district_name
        existing.sector = sector_name
        existing.cell = cell_name
        await db.flush()
        return _t("account_created", lang)

    phone_variants = _phone_variants(phoneNumber)
    phone_conflict = (await db.execute(
        select(User).where(or_(*[User.phone == v for v in phone_variants]))
    )).scalar_one_or_none()
    stored_phone = None if phone_conflict else phoneNumber

    new_user = User(
        email=email,
        phone=stored_phone,
        full_name=name,
        hashed_password=hash_password(secrets.token_hex(16)),
        role=UserRole.COMMUNITY,
        is_active=True,
        is_verified=True,
        province=province_name,
        district=district_name,
        sector=sector_name,
        cell=cell_name,
        ussd_pin_hash=hash_password(pin),
    )
    db.add(new_user)
    await db.flush()
    log.info("ussd_user_created", phone=phoneNumber, name=name,
             province=province_name, district=district_name,
             sector=sector_name, cell=cell_name)
    return _t("account_created", lang)


# ── PIN setup flow (web user logging in for the first time via USSD) ──────────
# parts: [lang, "2", pin, confirm]

async def _pin_setup_flow(
    parts: list[str], user: User, lang: str, db: AsyncSession
) -> str:
    depth = len(parts)

    if depth == 2:
        return _t("setup_pin", lang)

    pin = parts[2]
    if not pin.isdigit() or len(pin) != 4:
        return _t("pin_invalid", lang)

    if depth == 3:
        return _t("confirm_pin", lang)

    confirm = parts[3]
    if pin != confirm:
        return _t("pin_mismatch", lang)

    user.ussd_pin_hash = hash_password(pin)
    await db.flush()
    log.info("ussd_pin_set", user_id=str(user.id))
    return _t("pin_set", lang)


# ── Service flows (authenticated user) ───────────────────────────────────────
# sub_parts = parts[3:] = [main, sub1, sub2, ...]
# sub_depth = len(sub_parts): 1 = only main chosen, 2 = first sub chosen, etc.

async def _service_flow(
    sub_parts: list[str], main: str, lang: str,
    user: User, db: AsyncSession, phoneNumber: str,
) -> str:
    sub_depth = len(sub_parts)

    # ══════════════════════════════════════════════════════════════════════════
    # 1 - REPORT WATER ISSUE
    # sub_parts: [main, cat, urgency, provider_idx, confirm]
    # ══════════════════════════════════════════════════════════════════════════
    if main == "1":
        if sub_depth == 1:
            return _t("report_cat", lang)

        cat = sub_parts[1]
        if cat == "0":
            return _t("main_menu", lang)
        if cat not in _CAT_MAP:
            return _t("report_cat", lang)

        if sub_depth == 2:
            return _t("report_urgency", lang)

        urg = sub_parts[2]
        if urg == "0":
            return _t("report_cat", lang)
        if urg not in _URG_MAP:
            return _t("report_urgency", lang)

        providers = await _fetch_providers(db)
        if sub_depth == 3:
            return _provider_menu(providers, lang)

        prov_idx = sub_parts[3]
        if prov_idx == "0":
            return _t("report_urgency", lang)
        provider = _pick_provider(providers, prov_idx)
        if not provider:
            return _provider_menu(providers, lang)

        if sub_depth == 4:
            cat_name = (_CAT_EN if lang == "en" else _CAT_RW)[cat]
            urg_name = (_URG_EN if lang == "en" else _URG_RW)[urg]
            return _t("report_confirm", lang,
                      cat=cat_name, urgency=urg_name,
                      provider=provider.organization_name)

        confirm = sub_parts[4]
        if confirm == "0":
            return _t("main_menu", lang)
        if confirm != "1":
            return _t("invalid", lang)

        from app.core.sla import classify_priority, sla_deadline_for
        from app.models.report import PriorityClass

        _loc = ", ".join(filter(None, [user.sector, user.district, user.province])) or "Rwanda"
        ref = _gen_ref("RPT")
        priority = classify_priority(_CAT_MAP[cat].value, _URG_MAP[urg].value)
        report = Report(
            user_id=user.id,
            provider_id=provider.id,
            category=_CAT_MAP[cat],
            urgency=_URG_MAP[urg],
            priority_class=PriorityClass(priority),
            reference_number=ref,
            title=f"USSD: {_CAT_EN[cat]}",
            description=(
                f"{_CAT_EN[cat]} issue reported via USSD. "
                f"Urgency: {_URG_EN[urg]}. "
                f"Reporter: {user.full_name}, {phoneNumber}. "
                f"Location: {_loc}."
            ),
            province=user.province,
            district=user.district,
            sector=user.sector,
        )
        db.add(report)
        await db.flush()
        report.sla_deadline = sla_deadline_for(_CAT_MAP[cat].value, report.created_at, priority_class=priority)
        log.info("ussd_report_created", report_id=str(report.id), ref=ref, phone=phoneNumber)
        try:
            await notify_user(
                db, user_id=provider.user_id,
                notification_type="report_update",
                title=f"New {_CAT_EN[cat]} report (USSD)",
                body=(
                    f"{user.full_name} ({phoneNumber}) reported a {_CAT_EN[cat].lower()} issue. "
                    f"Urgency: {_URG_EN[urg]}. Location: {_loc}. Ref: {ref}."
                ),
                reference_id=str(report.id), reference_type="report",
            )
        except Exception:
            log.warning("ussd_notify_failed", report_id=str(report.id))
        # SMS confirmation to community member
        sms_to = _sms_phone(user, phoneNumber)
        sms_msg = (
            f"Temba: Your water issue report has been submitted.\n"
            f"Issue: {_CAT_EN[cat]} | Urgency: {_URG_EN[urg]}\n"
            f"Tracking code: {ref}\n"
            f"Track at temba.rw or dial *384*36640#"
        )
        asyncio.create_task(_sms(sms_to, sms_msg))
        return _t("report_submitted", lang, ref=ref)

    # ══════════════════════════════════════════════════════════════════════════
    # 2 - TRACK MY REPORTS  (with verify + rate for resolution_submitted)
    # sub_parts: [main] → show list
    # sub_parts: [main, report_idx] → show verify prompt for that report
    # sub_parts: [main, report_idx, verdict] → process verdict
    # sub_parts: [main, report_idx, verdict, rating] → save rating (1-5)
    # ══════════════════════════════════════════════════════════════════════════
    if main == "2":
        rows = list((await db.execute(
            select(Report)
            .where(Report.user_id == user.id)
            .order_by(Report.created_at.desc())
            .limit(5)
        )).scalars().all())
        if not rows:
            return _t("no_reports", lang)

        # Just listing — no sub-selection yet
        if sub_depth == 1:
            smap = _STATUS_EN if lang == "en" else _STATUS_RW
            pending = [r for r in rows if r.status == ReportStatus.RESOLUTION_SUBMITTED]
            lines = []
            for i, r in enumerate(rows, 1):
                st = smap.get(r.status.value, r.status.value)
                marker = " [VERIFY]" if r.status == ReportStatus.RESOLUTION_SUBMITTED else ""
                lines.append(f"{i}. {r.category.value}: {st}{marker}")
            hdr = "CON Your reports:\n" if lang == "en" else "CON Raporo zawe:\n"
            if pending:
                hdr += ("(Select a [VERIFY] report to confirm resolution)\n" if lang == "en"
                        else "(Hitamo raporo [VERIFY] kwemeza igisubizo)\n")
            return hdr + "\n".join(lines) + "\n0. Back"

        # User selected a report
        try:
            idx = int(sub_parts[1]) - 1
            if not (0 <= idx < len(rows)):
                return _t("main_menu", lang)
        except ValueError:
            if sub_parts[1] == "0":
                return _t("main_menu", lang)
            return _t("invalid", lang)

        report = rows[idx]

        # Report not in resolution_submitted or recently verified → just show status
        if report.status not in (ReportStatus.RESOLUTION_SUBMITTED, ReportStatus.VERIFIED):
            smap = _STATUS_EN if lang == "en" else _STATUS_RW
            ref = report.reference_number or _short_id(report.id)
            st = smap.get(report.status.value, report.status.value)
            return f"END {ref}\n{report.category.value}: {st}"

        # Show verify prompt
        if sub_depth == 2:
            ref = report.reference_number or _short_id(report.id)
            if lang == "en":
                return (f"CON Report: {ref}\nWas the issue resolved?\n"
                        "1. Yes, resolved\n2. Partially\n3. Not resolved\n0. Back")
            else:
                return (f"CON Raporo: {ref}\nIkibazo cyakemutse?\n"
                        "1. Yego, cyakemutse\n2. Igice\n3. Ntabwo cyakemutse\n0. Subira")

        verdict = sub_parts[2]
        if verdict == "0":
            return _t("main_menu", lang)

        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)

        if verdict == "1":
            # Verified — update status (skip if already verified from previous USSD step)
            if report.status != ReportStatus.VERIFIED:
                report.status = ReportStatus.VERIFIED
                report.verified_at = now
                await db.flush()

            # Show rating prompt
            if sub_depth == 3:
                if lang == "en":
                    return ("CON Rate the resolution (1-5):\n"
                            "1. Poor\n2. Fair\n3. Good\n4. Very Good\n5. Excellent\n0. Skip")
                else:
                    return ("CON Shyira amanota (1-5):\n"
                            "1. Nabi\n2. Bisanzwe\n3. Byiza\n4. Byiza cyane\n5. Byiza rwose\n0. Kureka")

            # Save rating
            rating_val = sub_parts[3] if sub_depth > 3 else "0"
            if rating_val in ("1", "2", "3", "4", "5"):
                from app.models.rating import Rating as _Rating
                r = _Rating(report_id=report.id, provider_id=report.provider_id, score=int(rating_val))
                db.add(r)
                await db.flush()
                star = "★" * int(rating_val)
                if lang == "en":
                    return f"END Thank you for your {star} rating!\nYour feedback helps improve water services."
                else:
                    return f"END Murakoze ku manota yanyu {star}!\nIbitekerezo byanyu bifasha kunoza serivisi z'amazi."

            # Skipped rating
            if lang == "en":
                return "END Issue verified. Thank you!\nTrack at temba.rw"
            else:
                return "END Ikibazo cyemejwe. Murakoze!\nKurikirana kuri temba.rw"

        elif verdict == "2":
            report.reopen_count = (report.reopen_count or 0) + 1
            report.status = ReportStatus.MANAGEMENT_REVIEW if report.reopen_count >= 2 else ReportStatus.FOLLOW_UP_REQUIRED
            await db.flush()
            if lang == "en":
                return f"END Marked as partially resolved.\nStatus: {report.status.value.replace('_', ' ').title()}"
            else:
                return f"END Byashyizwe nk'igice cyakemutse.\nAho bigeze: {report.status.value}"

        elif verdict == "3":
            report.reopen_count = (report.reopen_count or 0) + 1
            report.status = ReportStatus.MANAGEMENT_REVIEW if report.reopen_count >= 2 else ReportStatus.IN_PROGRESS
            await db.flush()
            if lang == "en":
                return f"END Marked as not resolved. Reopened.\nStatus: {report.status.value.replace('_', ' ').title()}"
            else:
                return f"END Byashyizwe nk'ibitakemutse. Byafunguwe.\nAho bigeze: {report.status.value}"

        return _t("invalid", lang)

    # ══════════════════════════════════════════════════════════════════════════
    # 3 - BOOK APPOINTMENT
    # sub_parts: [main, provider_idx, reason, date_choice, time_choice, confirm]
    # ══════════════════════════════════════════════════════════════════════════
    if main == "3":
        providers = await _fetch_providers(db)

        if sub_depth == 1:
            return _provider_menu(providers, lang)

        prov_idx = sub_parts[1]
        if prov_idx == "0":
            return _t("main_menu", lang)
        provider = _pick_provider(providers, prov_idx)
        if not provider:
            return _provider_menu(providers, lang)

        if sub_depth == 2:
            return _t("appt_reason", lang)

        reason = sub_parts[2]
        if reason == "0":
            return _provider_menu(providers, lang)
        if reason not in _REASON_MAP:
            return _t("appt_reason", lang)

        if sub_depth == 3:
            return _date_menu(lang)

        date_choice = sub_parts[3]
        if date_choice == "0":
            return _t("appt_reason", lang)
        if date_choice not in ("1", "2", "3", "4"):
            return _date_menu(lang)

        if sub_depth == 4:
            return _t("appt_time", lang)

        time_choice = sub_parts[4]
        if time_choice == "0":
            return _date_menu(lang)
        if time_choice not in _TIME_SLOTS:
            return _t("appt_time", lang)

        appt_date = _date_from_idx(date_choice)
        appt_time = _TIME_SLOTS[time_choice]

        if sub_depth == 5:
            return _t("appt_confirm", lang,
                      provider=provider.organization_name,
                      date=appt_date.strftime("%a %d %b %Y"),
                      time=appt_time)

        confirm = sub_parts[5]
        if confirm == "0":
            return _t("main_menu", lang)
        if confirm != "1":
            return _t("invalid", lang)

        _appt_loc = ", ".join(filter(None, [user.sector, user.district, user.province])) or "Rwanda"
        _reason_label = _APPT_REASON_EN.get(_REASON_MAP[reason].value, _REASON_MAP[reason].value)
        appt = Appointment(
            user_id=user.id,
            provider_id=provider.id,
            reason=_REASON_MAP[reason],
            appointment_date=appt_date,
            appointment_time=appt_time,
            meeting_type=MeetingType.IN_PERSON,
            status=AppointmentStatus.PENDING,
            notes=(
                f"[USSD] {_reason_label}. "
                f"Reporter: {user.full_name}, {phoneNumber}. "
                f"Location: {_appt_loc}."
            ),
        )
        db.add(appt)
        await db.flush()
        log.info("ussd_appointment_created", appt_id=str(appt.id), phone=phoneNumber)
        try:
            await notify_user(
                db, user_id=provider.user_id,
                notification_type="appointment_update",
                title="New appointment request (USSD)",
                body=(
                    f"{user.full_name} ({phoneNumber}) booked a {_reason_label.lower()} appointment "
                    f"for {appt_date.strftime('%d %b %Y')} at {appt_time}. Location: {_appt_loc}."
                ),
                reference_id=str(appt.id), reference_type="appointment",
            )
        except Exception:
            log.warning("ussd_notify_failed", appt_id=str(appt.id))
        # SMS confirmation to community member
        appt_ref = _short_id(appt.id)
        sms_to = _sms_phone(user, phoneNumber)
        sms_msg = (
            f"Temba: Appointment booked!\n"
            f"Provider: {provider.organization_name}\n"
            f"Date: {appt_date.strftime('%d %b %Y')} at {appt_time}\n"
            f"Tracking code: {appt_ref}\n"
            f"Track at temba.rw or dial *384*36640#"
        )
        asyncio.create_task(_sms(sms_to, sms_msg))
        return _t("appt_submitted", lang, ref=appt_ref)

    # ══════════════════════════════════════════════════════════════════════════
    # 4 - MY APPOINTMENTS
    # ══════════════════════════════════════════════════════════════════════════
    if main == "4":
        rows = list((await db.execute(
            select(Appointment)
            .where(Appointment.user_id == user.id)
            .order_by(Appointment.created_at.desc())
            .limit(3)
        )).scalars().all())
        if not rows:
            return _t("no_appts", lang)
        smap = _STATUS_EN if lang == "en" else _STATUS_RW
        rmap = _APPT_REASON_EN if lang == "en" else _APPT_REASON_RW
        lines = "\n".join(
            f"#{_short_id(a.id)} {rmap.get(a.reason.value, a.reason.value)}: {smap.get(a.status.value, a.status.value)}"
            for a in rows
        )
        return _t("appt_track_header", lang) + lines

    # ══════════════════════════════════════════════════════════════════════════
    # 5 - SERVICE REQUEST STATUS
    # ══════════════════════════════════════════════════════════════════════════
    if main == "5":
        rows = list((await db.execute(
            select(ServiceRequest)
            .where(ServiceRequest.user_id == user.id)
            .order_by(ServiceRequest.created_at.desc())
            .limit(3)
        )).scalars().all())
        if not rows:
            return _t("no_svc", lang)
        smap = _STATUS_EN if lang == "en" else _STATUS_RW
        lines = "\n".join(
            f"#{_short_id(s.id)} {s.request_type.value}: {smap.get(s.status.value, s.status.value)}"
            for s in rows
        )
        return _t("svc_track_header", lang) + lines

    # ══════════════════════════════════════════════════════════════════════════
    # 6 - SUBMIT SERVICE REQUEST
    # sub_parts: [main, svc_type, provider_idx, urgency, confirm]
    # ══════════════════════════════════════════════════════════════════════════
    if main == "6":
        if sub_depth == 1:
            return _t("svc_type", lang)

        svc = sub_parts[1]
        if svc == "0":
            return _t("main_menu", lang)
        if svc not in _SVC_MAP:
            return _t("svc_type", lang)

        providers = await _fetch_providers(db)
        if sub_depth == 2:
            return _provider_menu(providers, lang)

        prov_idx = sub_parts[2]
        if prov_idx == "0":
            return _t("svc_type", lang)
        provider = _pick_provider(providers, prov_idx)
        if not provider:
            return _provider_menu(providers, lang)

        if sub_depth == 3:
            return _t("svc_urgency", lang)

        urg = sub_parts[3]
        if urg == "0":
            return _provider_menu(providers, lang)
        if urg not in _SVC_URG_MAP:
            return _t("svc_urgency", lang)

        if sub_depth == 4:
            svc_name = (_SVC_EN if lang == "en" else _SVC_RW)[svc]
            urg_name = (_SVC_URG_EN if lang == "en" else _SVC_URG_RW)[urg]
            return _t("svc_confirm", lang,
                      svc=svc_name, urgency=urg_name,
                      provider=provider.organization_name)

        confirm = sub_parts[4]
        if confirm == "0":
            return _t("main_menu", lang)
        if confirm != "1":
            return _t("invalid", lang)

        _svc_loc = ", ".join(filter(None, [user.sector, user.district, user.province])) or "Rwanda"
        svc_ref = _gen_ref("SRQ")
        sr = ServiceRequest(
            user_id=user.id,
            provider_id=provider.id,
            request_type=_SVC_MAP[svc],
            urgency=_SVC_URG_MAP[urg],
            reference_number=svc_ref,
            description=(
                f"{_SVC_EN[svc]} request via USSD. "
                f"Urgency: {_SVC_URG_EN[urg]}. "
                f"Reporter: {user.full_name}, {phoneNumber}. "
                f"Location: {_svc_loc}."
            ),
            province=user.province,
            district=user.district,
            sector=user.sector,
            address_detail=_svc_loc if _svc_loc != "Rwanda" else None,
        )
        db.add(sr)
        await db.flush()
        log.info("ussd_service_request_created", sr_id=str(sr.id), ref=svc_ref, phone=phoneNumber)
        try:
            await notify_user(
                db, user_id=provider.user_id,
                notification_type="service_request_update",
                title="New service request (USSD)",
                body=(
                    f"{user.full_name} ({phoneNumber}) submitted a {_SVC_EN[svc].lower()} request. "
                    f"Urgency: {_SVC_URG_EN[urg]}. Location: {_svc_loc}. Ref: {svc_ref}."
                ),
                reference_id=str(sr.id), reference_type="service_request",
            )
        except Exception:
            log.warning("ussd_notify_failed", sr_id=str(sr.id))
        # SMS confirmation to community member
        sms_to = _sms_phone(user, phoneNumber)
        sms_msg = (
            f"Temba: Service request submitted!\n"
            f"Service: {_SVC_EN[svc]} | Urgency: {_SVC_URG_EN[urg]}\n"
            f"Provider: {provider.organization_name}\n"
            f"Tracking code: {svc_ref}\n"
            f"Track at temba.rw or dial *384*36640#"
        )
        asyncio.create_task(_sms(sms_to, sms_msg))
        return _t("svc_submitted", lang, ref=svc_ref)

    return _t("main_menu", lang)
