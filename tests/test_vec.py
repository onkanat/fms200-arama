import math

from fms200_arama.vec import embed, cosine


def test_boyut_768():
    assert len(embed("fms-200 modul")) == 768


def test_l2_normalize():
    v = embed("a b c d e f")
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6


def test_ayni_metin_ayni_vektor():
    assert embed("istasyon modulu") == embed("istasyon modulu")


def test_ayni_metin_skor_1():
    assert cosine(embed("istasyon plc program"), embed("istasyon plc program")) > 0.99


def test_alakasiz_dusuk():
    assert cosine(embed("istasyon plc program"), embed("hava durumu yagis")) < 0.3


def test_bos_metin_sifir():
    assert embed("") == [0.0] * 768
