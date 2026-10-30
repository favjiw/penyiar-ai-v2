"""Generator Blocker (FR-1): tema → 2–3 varian rundown Opening, 1–3 topik, Closing.

Keluaran LLM divalidasi terhadap aturan FR-1. Bila parsing atau validasi gagal,
permintaan diulang (maksimal MAX_RETRIES kali) dengan daftar masalahnya; tetap gagal → galat ke UI.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass, field

from app.blocker.store import BlockerStore, new_blocker_id, normalize, now_iso
from app.llm import LLMClient, LLMError, register_mock
from app.prompts import load_prompt
from app.schemas import (
    Blocker,
    BlockerPoint,
    BlockerTopic,
    DraftVariant,
    DraftVariants,
    GenerateBlockerRequest,
)

logger = logging.getLogger(__name__)

MIN_POINTS, MAX_POINTS = 3, 5
MAX_RETRIES = 2  # ulang parse atau validasi; total percobaan = 1 + MAX_RETRIES
MAX_OPENING_POINTS = 3
# Angka di poin hampir selalu klaim spesifik (tahun, persen, harga): tandai untuk dicek operator.
_DIGIT = re.compile(r"\d")


class BlockerGenerationError(RuntimeError):
    def __init__(self, message: str, issues: list[str] | None = None):
        super().__init__(message)
        self.issues = issues or []


@dataclass
class GenerationMeta:
    model: str
    prompt_version: str
    latency_ms: int
    attempts: int
    issues_first_attempt: list[str] = field(default_factory=list)


def validate_variant(variant: DraftVariant, jumlah_topik: int) -> list[str]:
    """Masalah yang membuat varian tidak layak dipakai (bukan sekadar perlu dirapikan)."""
    issues = []
    if len(variant.topics) < jumlah_topik:
        issues.append(f"'{variant.variant_label}': {len(variant.topics)} topik, diminta {jumlah_topik}")
    for i, topic in enumerate(variant.topics[:jumlah_topik], 1):
        if len(topic.poin) < MIN_POINTS:
            issues.append(f"'{variant.variant_label}' topik {i}: {len(topic.poin)} poin, minimal {MIN_POINTS}")
        for name in ("judul", "sudut_pandang", "pertanyaan_penonton", "transisi"):
            if not getattr(topic, name).strip():
                issues.append(f"'{variant.variant_label}' topik {i}: {name} kosong")
    if not variant.opening.hook.strip() or not variant.closing.rangkuman.strip():
        issues.append(f"'{variant.variant_label}': opening.hook atau closing.rangkuman kosong")
    return issues


def validate_variants(drafts: DraftVariants, req: GenerateBlockerRequest) -> list[str]:
    issues = []
    if len(drafts.variants) < req.jumlah_varian:
        issues.append(f"{len(drafts.variants)} varian, diminta {req.jumlah_varian}")
    labels = [v.variant_label.strip().lower() for v in drafts.variants]
    if len(set(labels)) < len(labels):
        issues.append("variant_label kembar; tiap varian harus beda sudut pandang")
    for v in drafts.variants[: req.jumlah_varian]:
        issues.extend(validate_variant(v, req.jumlah_topik))
    return issues


def to_blocker(variant: DraftVariant, req: GenerateBlockerRequest, generation_id: str) -> Blocker:
    """Draf LLM → Blocker: potong kelebihan, beri id, dan tandai poin berangka sebagai perlu_cek."""
    topics = [
        BlockerTopic(
            id="",
            judul=t.judul.strip(),
            sudut_pandang=t.sudut_pandang.strip(),
            poin=[
                BlockerPoint(id="", text=p.text.strip(), perlu_cek=p.perlu_cek or bool(_DIGIT.search(p.text)))
                for p in t.poin[:MAX_POINTS]
            ],
            pertanyaan_penonton=t.pertanyaan_penonton.strip(),
            transisi=t.transisi.strip(),
        )
        for t in variant.topics[: req.jumlah_topik]
    ]
    opening = variant.opening.model_copy(update={"poin": variant.opening.poin[:MAX_OPENING_POINTS]})
    return normalize(
        Blocker(
            id=new_blocker_id(req.tema),
            tema=req.tema.strip(),
            catatan=req.catatan.strip(),
            created_at=now_iso(),
            variant_label=variant.variant_label.strip(),
            opening=opening,
            topics=topics,
            closing=variant.closing,
            generation_id=generation_id,
        )
    )


def build_prompt(req: GenerateBlockerRequest, hindari: list[str] | None = None, issues: list[str] | None = None) -> str:
    lines = [
        f"TEMA: {req.tema.strip()}",
        f"JUMLAH_TOPIK: {req.jumlah_topik}",
        f"JUMLAH_VARIAN: {req.jumlah_varian}",
    ]
    if req.catatan.strip():
        lines.append(f"CATATAN PRODUSER (sasaran penonton, nuansa, hal yang dihindari): {req.catatan.strip()}")
    if hindari:
        lines.append("Varian yang sudah ada (pakai sudut pandang yang berbeda dari ini): " + "; ".join(hindari))
    if issues:
        lines.append("Jawaban sebelumnya ditolak karena: " + "; ".join(issues) + ". Perbaiki.")
    return "\n".join(lines)


class BlockerGenerator:
    def __init__(self, llm: LLMClient, model: str, store: BlockerStore, temperature: float = 0.9):
        self._llm, self._model, self._store = llm, model, store
        self._temperature = temperature
        self.prompt = load_prompt("blocker")

    async def _draft(self, req: GenerateBlockerRequest, hindari: list[str] | None) -> tuple[DraftVariants, GenerationMeta]:
        system = self.prompt.render(jumlah_topik=req.jumlah_topik, jumlah_varian=req.jumlah_varian)
        start = time.perf_counter()
        issues: list[str] = []
        first_issues: list[str] = []
        for attempt in range(1, MAX_RETRIES + 2):
            resp = await self._llm.generate(
                build_prompt(req, hindari, issues),
                model=self._model,
                system_instruction=system,
                response_schema=DraftVariants,
                temperature=self._temperature,
            )
            if resp.parse_error:
                issues = [f"JSON tidak sesuai skema ({resp.parse_error[:200]})"]
            else:
                drafts = DraftVariants.model_validate(resp.parsed)
                issues = validate_variants(drafts, req)
                if not issues:
                    meta = GenerationMeta(
                        resp.model, self.prompt.version, int((time.perf_counter() - start) * 1000), attempt, first_issues
                    )
                    return drafts, meta
            if attempt == 1:
                first_issues = issues
            if attempt <= MAX_RETRIES:
                logger.warning("Blocker '%s' ditolak (percobaan %d/%d), ulang: %s", req.tema, attempt, MAX_RETRIES + 1, issues)
        raise BlockerGenerationError(f"Generator blocker gagal setelah {MAX_RETRIES + 1} percobaan; coba lagi atau ubah tema", issues)

    async def generate(self, req: GenerateBlockerRequest) -> tuple[list[Blocker], GenerationMeta]:
        try:
            drafts, meta = await self._draft(req, None)
        except LLMError as e:
            raise BlockerGenerationError(str(e)) from e
        generation_id = f"gen_{secrets.token_hex(4)}"
        blockers = [self._store.save(to_blocker(v, req, generation_id)) for v in drafts.variants[: req.jumlah_varian]]
        return blockers, meta

    async def regenerate_variant(self, blocker_id: str, hindari: list[str]) -> tuple[Blocker, GenerationMeta]:
        """Buat ulang satu varian draf dengan tema dan jumlah topik yang sama."""
        old = self._store.get(blocker_id)
        req = GenerateBlockerRequest(tema=old.tema, catatan=old.catatan, jumlah_topik=len(old.topics), jumlah_varian=2)
        avoid = [old.variant_label, *hindari]
        try:
            drafts, meta = await self._draft(req, avoid)
        except LLMError as e:
            raise BlockerGenerationError(str(e)) from e
        labels = {a.strip().lower() for a in avoid}
        pick = next((v for v in drafts.variants if v.variant_label.strip().lower() not in labels), drafts.variants[0])
        return self._store.save(to_blocker(pick, req, old.generation_id or "")), meta


# ── Mock (LLM_MODE=mock) ─────────────────────────────────────────────────────

_MOCK_ANGLES = [
    ("Pengalaman pribadi", "cerita pengalaman sehari-hari soal {tema}"),
    ("Mitos atau fakta", "anggapan umum soal {tema} yang sering kedengeran"),
    ("Tips ala anak kos", "tips praktis soal {tema} buat mahasiswa"),
    ("Dulu vs sekarang", "perubahan {tema} dari zaman dulu ke sekarang"),
]


def _mock_drafts(prompt: str, call_no: int) -> dict:
    def field_of(name: str, default: str) -> str:
        m = re.search(rf"^{name}: (.+)$", prompt, flags=re.MULTILINE)
        return m.group(1).strip() if m else default

    tema = field_of("TEMA", "Tema")
    n_topik = int(field_of("JUMLAH_TOPIK", "3"))
    n_varian = int(field_of("JUMLAH_VARIAN", "3"))
    variants = []
    for k in range(n_varian):
        label, angle = _MOCK_ANGLES[(k + call_no - 1) % len(_MOCK_ANGLES)]
        topics = [
            {
                "judul": f"{tema}: bagian {i}",
                "sudut_pandang": angle.format(tema=tema.lower()),
                # Tanpa angka: poin berangka otomatis ditandai perlu_cek
                "poin": [{"text": f"poin {ke} soal {tema.lower()} ({label.lower()})", "perlu_cek": False} for ke in ("pertama", "kedua", "ketiga", "keempat")],
                "pertanyaan_penonton": f"Kalau lo, gimana soal {tema.lower()}?",
                "transisi": "Oke, lanjut ke obrolan berikutnya ya." if i < n_topik else "Oke, kita rangkum dulu ya.",
            }
            for i in range(1, n_topik + 1)
        ]
        variants.append(
            {
                "variant_label": label,
                "opening": {"hook": f"Sobat Hits, ngomongin {tema.lower()} yuk!", "poin": ["sapa penonton", "kenalin tema"]},
                "topics": topics,
                "closing": {"rangkuman": f"{tema} ternyata seru dibahas", "ajakan": "ceritain pendapat kalian ke teman sebelah"},
            }
        )
    return {"variants": variants}


register_mock(DraftVariants, _mock_drafts)
