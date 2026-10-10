import os
import sqlite3

from fms200_arama.norm import norm, detect_lang


def test_norm_harf_arasi_bosluk():
    # Gerçek Scribd/DOSYA verisi: "o c h o p" -> "ochop"
    assert norm("o c h o p") == "ochop"


def test_norm_kelime_sonu_yapisir():
    # "TECHNICA L DESCRIPTION" -> "TECHNICAL DESCRIPTION"
    assert norm("TECHNICA L DESCRIPTION") == "TECHNICAL DESCRIPTION"


def test_norm_fms_birlesir():
    # Gerçek Scribd artifact'i: tek-harf dizisi bitişikleşir
    assert norm("F M S") == "FMS"
    assert norm("F M S 2 0 0") == "FMS200"


def test_norm_nbsp_temizler():
    assert "\xa0" not in norm("a\xa0b")


def test_norm_bosluk_sikistirir():
    assert norm("  a \n\n b  ") == "a b"


def test_norm_eksen_harfi_korunur():
    """Tek harfli X/Y/Z bir eksen etiketi olabilir — birleştirilmez (2026-10-10 düzeltmesi)."""
    assert norm("servo sürücü X ekseni") == "servo sürücü X ekseni"
    assert norm("servo drive Y axis") == "servo drive Y axis"
    assert norm("eje Z") == "eje Z"


def test_norm_diger_tek_harfler_yine_birlesir():
    """İstisna yalnız X/Y/Z: OCR boşluk onarımı (F M S) bozulmamalı."""
    assert norm("F M S 2 0 0") == "FMS200"
    assert norm("P L C") == "PLC"


def test_dil_tr():
    assert detect_lang("Bu sistem için kullanım kılavuzu ve montaj") == "tr"


def test_dil_es():
    assert detect_lang("La estación de rodamiento del sistema") == "es"


def test_dil_en():
    assert detect_lang("This is the procedure to change the station module") == "en"


def test_dil_bilinmeyen():
    assert detect_lang("12345 !!!") == "??"
