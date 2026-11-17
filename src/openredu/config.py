"""
OpenRedu configuration.

All API credentials are loaded from environment variables (.env file).
Never hardcode secrets here.
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# Always load the repository-level secrets, independent of the launch directory.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ── API credentials (from environment) ───────────────────────────────────────
ENTREZ_EMAIL   = os.getenv("ENTREZ_EMAIL", "")
ENTREZ_API_KEY = os.getenv("ENTREZ_API_KEY", "")
UMLS_API_KEY   = os.getenv("UMLS_API_KEY", "")
AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")

# ── URLs ──────────────────────────────────────────────────────────────────────
PMC_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
UMLS_BASE      = "https://uts-ws.nlm.nih.gov/rest"

# ── Rate limits ───────────────────────────────────────────────────────────────
ENTREZ_DELAY   = 0.11   # 10 req/sec with API key; use 0.34 without
BATCH_SIZE     = 500
UMLS_DELAY     = 0.25

ALLOWED_LICENSES = [
    "CC BY", "CC BY-SA", "CC BY-ND",
    "CC BY-NC", "CC BY-NC-SA", "CC BY-NC-ND",
]

# ── LLM model IDs ─────────────────────────────────────────────────────────────
MODELS = {
    # Curation
    "extraction_primary":        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "extraction_middle":         "mistral.mistral-large-3-675b-instruct",
    "extraction_escalate":       "us.anthropic.claude-sonnet-4-6",
    "classification_adjudicate": "us.anthropic.claude-sonnet-4-6",
    "verification":              "us.amazon.nova-pro-v1:0",   # independent text-only verifier (opt-in)
    # Mapping
    "standardization_llm":       "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "mapping_adjudicate":        "us.anthropic.claude-sonnet-4-6",
    "guideline_structuring":     "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # Tracking
    "gap_prioritization":        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # AssessmentSubagent is deterministic (no LLM)
}

MODEL_PROVIDERS = {
    "extraction_primary":        "bedrock_anthropic",
    "extraction_middle":         "bedrock_mistral",
    "extraction_escalate":       "bedrock_anthropic",
    "classification_adjudicate": "bedrock_anthropic",
    "standardization_llm":       "bedrock_anthropic",
    "mapping_adjudicate":        "bedrock_anthropic",
    "guideline_structuring":     "bedrock_anthropic",
    "gap_prioritization":        "bedrock_anthropic",
}

# TrackingMasterAgent threshold: encounters >= this → topic considered "completed"
COVERAGE_THRESHOLD = 1

# ── Non-radiology exclude keywords (used in gap-fill mode) ───────────────────
# These are always excluded regardless of modality — non-imaging figures.
# In gap-fill mode, modality-specific other-imaging excludes are bypassed,
# but these non-radiology terms are always kept.
NON_RADIOLOGY_EXCLUDE = [
    # pathology
    "histopath", "h&e", "hematoxylin", "microscop", "patholog", "biopsy specimen",
    "gross specimen", "gross pathol",
    # non-imaging figures
    "flowchart", "flow chart", "flow-chart", "diagram", "schematic", "algorithm",
    "study design", "protocol", "workflow", "timeline",
    # graphs/tables
    " table ", " bar graph", "bar chart", " pie chart", "kaplan-meier",
    # surgical/procedural photos
    "intraoperative", "laparoscop", "arthroscop", "colonoscop", "endoscop",
    "operative photo", "surgical photo",
]

# ── UMLS trusted sources ──────────────────────────────────────────────────────
TRUSTED_UMLS_SOURCES = {"MTH", "SNOMEDCT_US", "MSH", "ICD10CM", "NCI", "HPO"}

# ── Target modalities (10 original + 6 gap-fill) ─────────────────────────────
TARGET_MODALITIES = [
    # Original 10 (paper baseline, 2020-2026)
    "CT_CHEST", "MRI_BRAIN", "CT_ABDOMEN", "CXR",
    "CT_BRAIN", "MAMMOGRAM", "US_VASCULAR", "US_ABDOMEN",
    "US_PELVIS", "MRI_SPINE",
    # Gap-fill 6 promoted to full scan
    "MRI_MSK", "MSK_XRAY", "NM_NUCLEAR",
    "CT_CHEST_VASC", "MRI_NEURO_SPINE", "US_GYN_TRANS",
    # ABR Core blueprint expansion (new 9)
    "MRI_ABDOMEN", "MRI_PELVIS",
    "GI_FLUOROSCOPY", "GU_FLUOROSCOPY",
    "BREAST_ULTRASOUND", "BREAST_MRI", "CARDIOVASCULAR_MRI",
    "MSK_CT", "MSK_ULTRASOUND",
]

# No active gap-fill modalities — all promoted to TARGET_MODALITIES.
# OBSTETRIC_ULTRASOUND reserved for future collection; no processed/ file exists yet.
GAP_FILL_MODALITIES = []

# Historical Phase 2 working candidates. Kept for provenance and not picked up
# by a production collection run. The authoritative expansion inventory is now
# ABR_COLLECTION_CANDIDATES in openredu.abr_taxonomy; mixed entries below are
# split there into figure-level ABR-aligned categories.
COLLECTION_EXPANSION_CANDIDATES = [
    "CT_NECK",
    "MRI_HEAD_NECK",
    "CARDIAC_MRI",
    "CARDIAC_CT",
    "FLUOROSCOPY_GI_GU",
    "CTA_ABDOMEN_PELVIS",
]

# This legacy list represented 15 regular + 3 gap-fill + 6 working candidates.
# It must not be reported as 24 standardized imaging categories.

# Earlier versions of the coverage analysis proposed excluding a set of curriculum
# topics (normal studies, staging/characterization tasks) from the denominator.
# That proposal is not applied: the canonical denominator includes every valid
# must-see topic. The topic list itself is curriculum data and is not distributed.
APDR_DENOMINATOR_EXCLUSION_HISTORY: list[str] = []

# Active analytic exclusions. Parser artifacts are handled separately by the
# stable-ID manifest at PATHS["apdr_parser_artifacts"].
NORMAL_STUDY_EXCLUSIONS: list[str] = []

# ── Paths ─────────────────────────────────────────────────────────────────────
# Repository root; all runtime data lives under <OPENREDU_HOME>/data (not distributed).
_BASE = Path(os.getenv("OPENREDU_HOME", Path(__file__).resolve().parents[2]))

PATHS = {
    "data":             _BASE / "data",
    "processed":        _BASE / "data" / "processed",
    "failed":           _BASE / "data" / "failed",
    "unmapped":         _BASE / "data" / "unmapped",
    "images":           _BASE / "data" / "images",
    "manifests":        _BASE / "data" / "manifests",
    "guidelines":       _BASE / "data" / "guidelines",
    "apdr_keywords":    _BASE / "data" / "guidelines" / "apdr_pmc_keywords.csv",
    "final_synonym_index": _BASE / "data" / "guidelines" / "final_synonym_index.json",
    "apdr_cui_corrections": _BASE / "data" / "guidelines" / "apdr_cui_corrections.json",
    "apdr_parser_artifacts": _BASE / "data" / "guidelines" / "apdr_parser_artifacts.json",
    "apdr_topic_normalization": _BASE / "data" / "guidelines" / "apdr_topic_normalization.json",
    "division_anchors":     _BASE / "config" / "division_anchors.json",
    "case_diagnosis_mesh": _BASE / "data" / "guidelines" / "case_diagnosis_mesh.json",
    # Optional cache of earlier extraction records (development shortcut only)
    "cache_phase2_dir": Path(os.getenv("OPENREDU_PHASE2_CACHE_DIR", _BASE / "data" / "phase2_cache")),
}

# Ensure output directories exist at import time
for _key in ("processed", "failed", "unmapped", "images", "manifests"):
    PATHS[_key].mkdir(parents=True, exist_ok=True)

# ── Abbreviation map (for concept normalization) ──────────────────────────────
ABBR_MAP = {
    "acl": "anterior cruciate ligament",
    "avm": "arteriovenous malformation",
    "bph": "benign prostatic hyperplasia",
    "cad": "coronary artery disease",
    "cns": "central nervous system",
    "copd": "chronic obstructive pulmonary disease",
    "ct": "computed tomography",
    "cta": "computed tomography angiography",
    "ctpa": "computed tomography pulmonary angiography",
    "cvst": "cerebral venous sinus thrombosis",
    "dcis": "ductal carcinoma in situ",
    "ddx": "differential diagnosis",
    "dvt": "deep vein thrombosis",
    "dwi": "diffusion-weighted imaging",
    "edh": "epidural hematoma",
    "fdg": "fluorodeoxyglucose",
    "flair": "fluid-attenuated inversion recovery",
    "gbm": "glioblastoma multiforme",
    "gi": "gastrointestinal",
    "gist": "gastrointestinal stromal tumor",
    "gre": "gradient echo",
    "gu": "genitourinary",
    "hcc": "hepatocellular carcinoma",
    "hrct": "high-resolution computed tomography",
    "idc": "invasive ductal carcinoma",
    "ilc": "invasive lobular carcinoma",
    "ipmn": "intraductal papillary mucinous neoplasm",
    "ivc": "inferior vena cava",
    "mca": "middle cerebral artery",
    "mri": "magnetic resonance imaging",
    "msk": "musculoskeletal",
    "nicu": "neonatal intensive care unit",
    "nsclc": "non-small cell lung cancer",
    "pad": "peripheral arterial disease",
    "pca": "prostate cancer",
    "pcl": "posterior cruciate ligament",
    "pe": "pulmonary embolism",
    "pnet": "pancreatic neuroendocrine tumor",
    "pres": "posterior reversible encephalopathy syndrome",
    "rcc": "renal cell carcinoma",
    "sah": "subarachnoid hemorrhage",
    "sdh": "subdural hematoma",
    "stir": "short tau inversion recovery",
    "swi": "susceptibility weighted imaging",
    "tb": "tuberculosis",
    "tbi": "traumatic brain injury",
    "tte": "transthoracic echocardiography",
    "us": "ultrasound",
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "is", "was", "are", "were", "be", "been",
    "has", "have", "had", "not", "but", "if", "its", "this", "that",
    "case", "report", "patient", "presented", "showing", "shown",
}

# ── Modality configuration (10 target modalities) ─────────────────────────

MODALITY_CONFIG = {'CT_ABDOMEN': {'anatomy': 'abdomen',
                'diagnosis_normalization': {' fnh ': 'Focal nodular hyperplasia',
                                            ' gist ': 'Gastrointestinal stromal tumor',
                                            ' hcc ': 'Hepatocellular carcinoma',
                                            ' pnet ': 'Pancreatic neuroendocrine tumor',
                                            ' rcc ': 'Renal cell carcinoma',
                                            'angiomyolipoma': 'Renal angiomyolipoma',
                                            'appendicitis': 'Acute appendicitis',
                                            'cholangiocarcinoma': 'Cholangiocarcinoma',
                                            'focal nodular hyperplasia': 'Focal nodular hyperplasia',
                                            'gastrointestinal stromal': 'Gastrointestinal stromal tumor',
                                            'hemangioma': 'Hepatic hemangioma',
                                            'hepatocellular carcinoma': 'Hepatocellular carcinoma',
                                            'hepatoma': 'Hepatocellular carcinoma',
                                            'ipmn': 'Intraductal papillary mucinous neoplasm',
                                            'lymphoma': 'Lymphoma',
                                            'pancreatic ductal adenocarcinoma': 'Pancreatic adenocarcinoma',
                                            'pancreatic neuroendocrine': 'Pancreatic neuroendocrine tumor',
                                            'pdac': 'Pancreatic adenocarcinoma',
                                            'pheochromocytoma': 'Pheochromocytoma',
                                            'renal cell carcinoma': 'Renal cell carcinoma',
                                            'transitional cell': 'Urothelial carcinoma',
                                            'urothelial carcinoma': 'Urothelial carcinoma'},
                'exclude_keywords': ['ct brain',
                                     'brain ct',
                                     'ct head',
                                     'head ct',
                                     'cranial ct',
                                     'ct chest',
                                     'chest ct',
                                     'ct of the chest',
                                     'ct thorax',
                                     'ct pulmonary',
                                     'hrct',
                                     'ctpa',
                                     'ct spine',
                                     'spine ct',
                                     'ct of the spine',
                                     'ct lumbar',
                                     'lumbar ct',
                                     'ct cervical spine',
                                     'ct neck',
                                     'neck ct',
                                     'ct of the neck',
                                     'ct chest abdomen',
                                     'whole body ct',
                                     'pan-scan',
                                     'chest x-ray',
                                     'chest xray',
                                     'chest radiograph',
                                     ' cxr ',
                                     'abdominal x-ray',
                                     'plain abdominal',
                                     'mri abdomen',
                                     'abdominal mri',
                                     'magnetic resonance',
                                     'abdominal ultrasound',
                                     'hepatic ultrasound',
                                     'sonograph',
                                     'pet scan',
                                     'pet-ct',
                                     'fdg',
                                     'histopath',
                                     'h&e',
                                     'hematoxylin',
                                     'microscop',
                                     'intraoperative',
                                     'laparoscop',
                                     'colonoscop',
                                     'flowchart',
                                     'flow chart',
                                     'flow-chart',
                                     ' diagram',
                                     'schematic',
                                     'algorithm',
                                     'study design',
                                     'protocol',
                                     'workflow',
                                     ' table ',
                                     'timeline',
                                     ' bar graph',
                                     'bar chart',
                                     ' pie chart'],
                'imaging_modality': 'CT',
                'include_keywords': ['ct abdomen',
                                     'abdominal ct',
                                     'ct of the abdomen',
                                     'ct scan abdomen',
                                     'ct of abdomen',
                                     'computed tomography abdomen',
                                     'computed tomography of the abdomen',
                                     'abdominopelvic ct',
                                     'ct abdomen and pelvis',
                                     'ct abdomen/pelvis',
                                     'ct pelvis',
                                     'pelvic ct',
                                     'ct of the pelvis',
                                     'contrast-enhanced ct abdomen',
                                     'contrast enhanced ct abdomen',
                                     'portal venous phase ct',
                                     'arterial phase ct',
                                     'cect abdomen',
                                     'cect of abdomen',
                                     'triple-phase ct',
                                     'triphasic ct',
                                     'ct of the liver',
                                     'liver ct',
                                     'hepatic ct',
                                     'ct of the pancreas',
                                     'pancreatic ct',
                                     'ct kidney',
                                     'renal ct',
                                     'ct of the kidney',
                                     'ct urography',
                                     'ct kub',
                                     'ct colonography',
                                     'virtual colonoscopy',
                                     'mdct abdomen',
                                     'non-contrast ct abdomen'],
                'llm_system_prompt': 'You are a radiology data curator specializing in abdominal CT. Extract '
                                     'structured information from abdominal/pelvic CT case report text.\n'
                                     'Return ONLY valid JSON with these exact fields:\n'
                                     '{\n'
                                     '  "finding": "primary CT abdomen finding (e.g. \'heterogeneous hepatic mass with '
                                     "arterial enhancement and portal venous washout', 'dilated common bile duct with "
                                     "distal obstructing stone', 'acute appendicitis with periappendiceal fat "
                                     'stranding\', \'splenic laceration with hemoperitoneum\')",\n'
                                     '  "diagnosis": "final clinical diagnosis (e.g. \'hepatocellular carcinoma\', '
                                     "'choledocholithiasis', 'acute appendicitis', 'renal cell carcinoma', 'acute "
                                     'pancreatitis\')",\n'
                                     '  "laterality": "right | left | bilateral | midline | N/A"\n'
                                     '}\n'
                                     '\n'
                                     'CRITICAL - Extraction priority:\n'
                                     '1. PRIMARY SOURCE: Use "Figure legend" and "Results text" as the PRIMARY source '
                                     'for finding extraction\n'
                                     '2. Extract: organ involved, density/enhancement pattern, size, secondary signs '
                                     '(fat stranding, free fluid, biliary dilatation, bowel obstruction)\n'
                                     '3. Note contrast phase if mentioned (non-contrast, arterial, portal venous, '
                                     'delayed)\n'
                                     '4. Only use "Case presentation" for additional clinical context\n'
                                     '\n'
                                     'CRITICAL - Diagnosis normalization:\n'
                                     '- "Hepatocellular carcinoma" NOT "HCC" or "hepatoma"\n'
                                     '- "Acute appendicitis" NOT just "appendicitis"\n'
                                     '- "Renal cell carcinoma" NOT "RCC"\n'
                                     '- "Gastrointestinal stromal tumor" NOT "GIST"\n'
                                     '- "Cholangiocarcinoma" (intrahepatic/extrahepatic as appropriate)\n'
                                     '- "Crohn disease" NOT "Crohn\'s disease"\n'
                                     '- "Pancreatic adenocarcinoma" NOT "PDAC"\n'
                                     '- "Intraductal papillary mucinous neoplasm" NOT "IPMN"\n'
                                     '\n'
                                     'Laterality: right/left for paired organs (kidney, adrenal, colon) | bilateral | '
                                     'midline for central structures (pancreas, aorta, bladder) | N/A for diffuse '
                                     'disease\n'
                                     '\n'
                                     "If uncertain, use 'unclear' or 'N/A'. Never return null.",
                'name': 'CT Abdomen',
                'search_keywords': ['CT abdomen',
                                    'abdominal CT',
                                    'abdominal computed tomography',
                                    'computed tomography abdomen',
                                    'CT of the abdomen',
                                    'CT pelvis',
                                    'abdominopelvic CT',
                                    'CT scan abdomen',
                                    'contrast-enhanced CT abdomen',
                                    'CT urography',
                                    'CT colonography']},
 'CT_BRAIN': {'anatomy': 'brain',
              'diagnosis_normalization': {' avm ': 'Arteriovenous malformation',
                                          ' cva ': 'Acute ischemic stroke',
                                          ' cvst ': 'Cerebral venous thrombosis',
                                          ' cvt ': 'Cerebral venous thrombosis',
                                          ' edh ': 'Epidural hematoma',
                                          ' gbm ': 'Glioblastoma',
                                          ' ich ': 'Intracerebral hemorrhage',
                                          ' sah ': 'Subarachnoid hemorrhage',
                                          ' sdh ': 'Subdural hematoma',
                                          ' tbi ': 'Traumatic brain injury',
                                          'arteriovenous malformation': 'Arteriovenous malformation',
                                          'brain abscess': 'Brain abscess',
                                          'brain metastases': 'Brain metastasis',
                                          'cerebral abscess': 'Brain abscess',
                                          'cerebral infarct': 'Acute ischemic stroke',
                                          'cerebral venous thrombosis': 'Cerebral venous thrombosis',
                                          'diffuse axonal injury': 'Diffuse axonal injury',
                                          'epidural hematoma': 'Epidural hematoma',
                                          'glioblastoma': 'Glioblastoma',
                                          'glioblastoma multiforme': 'Glioblastoma',
                                          'hydrocephalus': 'Hydrocephalus',
                                          'intracerebral hemorrhage': 'Intracerebral hemorrhage',
                                          'intraparenchymal hemorrhage': 'Intracerebral hemorrhage',
                                          'ischemic stroke': 'Acute ischemic stroke',
                                          'meningioma': 'Meningioma',
                                          'subarachnoid hemorrhage': 'Subarachnoid hemorrhage',
                                          'subdural hematoma': 'Subdural hematoma',
                                          'traumatic brain injury': 'Traumatic brain injury'},
              'exclude_keywords': ['ct chest',
                                   'chest ct',
                                   'ct of the chest',
                                   'ct thorax',
                                   'ct pulmonary',
                                   'hrct',
                                   'ctpa',
                                   'ct abdomen',
                                   'abdominal ct',
                                   'ct of the abdomen',
                                   'ct pelvis',
                                   'pelvic ct',
                                   'abdominopelvic ct',
                                   'ct spine',
                                   'spine ct',
                                   'ct of the spine',
                                   'ct lumbar',
                                   'lumbar ct',
                                   'ct cervical spine',
                                   'ct neck',
                                   'neck ct',
                                   'ct of the neck',
                                   'ct soft tissue neck',
                                   'ct head and neck',
                                   'whole body ct',
                                   'pan-scan',
                                   'mri brain',
                                   'brain mri',
                                   'magnetic resonance brain',
                                   'mri head',
                                   'head mri',
                                   'cranial mri',
                                   'flair',
                                   'diffusion-weighted',
                                   ' dwi ',
                                   ' adc ',
                                   'susceptibility-weighted',
                                   ' swi ',
                                   'chest x-ray',
                                   'chest xray',
                                   'chest radiograph',
                                   ' cxr ',
                                   'pet scan',
                                   'pet-ct',
                                   'fdg',
                                   'cerebral angiograph',
                                   'histopath',
                                   'h&e',
                                   'hematoxylin',
                                   'microscop',
                                   'intraoperative',
                                   'flowchart',
                                   'flow chart',
                                   'flow-chart',
                                   ' diagram',
                                   'schematic',
                                   'algorithm',
                                   'study design',
                                   'protocol',
                                   'workflow',
                                   ' table ',
                                   'timeline',
                                   ' bar graph',
                                   'bar chart',
                                   ' pie chart'],
              'imaging_modality': 'CT',
              'include_keywords': ['ct brain',
                                   'brain ct',
                                   'ct of the brain',
                                   'ct of brain',
                                   'ct head',
                                   'head ct',
                                   'ct of the head',
                                   'computed tomography brain',
                                   'computed tomography head',
                                   'brain computed tomography',
                                   'ct scan brain',
                                   'ct scan head',
                                   'non-contrast ct brain',
                                   'noncontrast ct brain',
                                   'ncct brain',
                                   'nect brain',
                                   'ncct head',
                                   'nect head',
                                   'non-enhanced ct brain',
                                   'unenhanced ct brain',
                                   'cta brain',
                                   'cta head',
                                   'ct angiography brain',
                                   'ct angiography head',
                                   'cerebral cta',
                                   'cranial cta',
                                   'ct perfusion brain',
                                   'ct perfusion head',
                                   'cranial ct',
                                   'ct cranial',
                                   'cranial computed tomography',
                                   'intracranial ct',
                                   'ct intracranial'],
              'llm_system_prompt': 'You are a radiology data curator specializing in brain CT. Extract structured '
                                   'information from brain/head CT case report text.\n'
                                   'Return ONLY valid JSON with these exact fields:\n'
                                   '{\n'
                                   '  "finding": "primary CT brain finding (e.g. \'hyperdense lesion in right basal '
                                   "ganglia consistent with intracerebral hemorrhage', 'loss of gray-white "
                                   "differentiation with sulcal effacement in left MCA territory', 'hypodense subdural "
                                   "collection along right convexity', 'subarachnoid hemorrhage filling basal "
                                   'cisterns\')",\n'
                                   '  "diagnosis": "final clinical diagnosis (e.g. \'intracerebral hemorrhage\', '
                                   "'acute ischemic stroke', 'subdural hematoma', 'subarachnoid hemorrhage', 'epidural "
                                   'hematoma\')",\n'
                                   '  "laterality": "right | left | bilateral | midline | N/A"\n'
                                   '}\n'
                                   '\n'
                                   'CRITICAL - Extraction priority:\n'
                                   '1. PRIMARY SOURCE: Use "Figure legend" and "Results text" as the PRIMARY source '
                                   'for finding extraction\n'
                                   '2. Extract CT brain-specific findings: density (hyperdense/hypodense/isodense), '
                                   'location (lobar, basal ganglia, thalamus, cerebellum, brainstem, subdural, '
                                   'epidural, subarachnoid), mass effect, midline shift, hydrocephalus\n'
                                   '3. For CTA: note vessel occlusion location (e.g. M1 segment occlusion)\n'
                                   '4. Only use "Case presentation" for additional clinical context\n'
                                   '\n'
                                   'CRITICAL - Diagnosis normalization:\n'
                                   '- "Intracerebral hemorrhage" NOT "ICH" or "intracranial hemorrhage"\n'
                                   '- "Acute ischemic stroke" NOT "CVA" or "cerebral infarction"\n'
                                   '- "Subdural hematoma" (add acute/subacute/chronic if mentioned) NOT "SDH"\n'
                                   '- "Subarachnoid hemorrhage" NOT "SAH"\n'
                                   '- "Epidural hematoma" NOT "EDH"\n'
                                   '- "Cerebral venous thrombosis" NOT "CVT" or "CVST"\n'
                                   '- "Glioblastoma" NOT "GBM" or "glioblastoma multiforme"\n'
                                   '- "Hydrocephalus" (add obstructive/communicating if mentioned)\n'
                                   '\n'
                                   'Laterality: right/left for hemispheric or lobar lesions | bilateral | midline '
                                   '(corpus callosum, cerebellar vermis, pineal) | N/A for diffuse processes (global '
                                   'edema, diffuse SAH)\n'
                                   '\n'
                                   "If uncertain, use 'unclear' or 'N/A'. Never return null.",
              'name': 'CT Brain',
              'search_keywords': ['CT brain',
                                  'brain CT',
                                  'CT head',
                                  'head CT',
                                  'brain computed tomography',
                                  'computed tomography brain',
                                  'non-contrast CT brain',
                                  'NCCT brain',
                                  'NECT brain',
                                  'CT angiography brain',
                                  'CTA brain',
                                  'CT perfusion brain']},
 'CT_CHEST': {'anatomy': 'chest',
              'diagnosis_normalization': {' ipf ': 'Idiopathic pulmonary fibrosis',
                                          ' pcp ': 'Pneumocystis pneumonia',
                                          ' pe ': 'Pulmonary embolism',
                                          ' tb ': 'Tuberculosis',
                                          ' uip ': 'UIP pattern',
                                          'adenocarcinoma': 'Lung adenocarcinoma',
                                          'aspergill': 'Pulmonary aspergillosis',
                                          'carcinoid': 'Pulmonary carcinoid tumor',
                                          'covid': 'COVID-19 pneumonia',
                                          'hamartoma': 'Pulmonary hamartoma',
                                          'idiopathic pulmonary fibrosis': 'Idiopathic pulmonary fibrosis',
                                          'mesothelioma': 'Mesothelioma',
                                          'non-small cell': 'Non-small cell lung cancer',
                                          'pneumocystis': 'Pneumocystis pneumonia',
                                          'pulmonary embolism': 'Pulmonary embolism',
                                          'sarcoid': 'Sarcoidosis',
                                          'sars-cov': 'COVID-19 pneumonia',
                                          'small cell': 'Small cell lung cancer',
                                          'squamous cell carcinoma': 'Squamous cell carcinoma of lung',
                                          'thymoma': 'Thymoma',
                                          'tuberculosis': 'Tuberculosis'},
              'exclude_keywords': ['ct brain',
                                   'brain ct',
                                   'ct head',
                                   'head ct',
                                   'ct of the brain',
                                   'cranial ct',
                                   'ncct brain',
                                   'ct abdomen',
                                   'abdominal ct',
                                   'ct of the abdomen',
                                   'ct pelvis',
                                   'pelvic ct',
                                   'abdominopelvic ct',
                                   'ct spine',
                                   'spine ct',
                                   'ct of the spine',
                                   'ct lumbar',
                                   'lumbar ct',
                                   'ct cervical spine',
                                   'ct thoracic spine',
                                   'ct neck',
                                   'neck ct',
                                   'ct of the neck',
                                   'ct chest abdomen',
                                   'ct chest and abdomen',
                                   'ct chest/abdomen',
                                   'whole body ct',
                                   'pan-scan',
                                   'chest x-ray',
                                   'chest xray',
                                   'chest radiograph',
                                   'chest x ray',
                                   ' cxr ',
                                   'plain chest',
                                   'chest film',
                                   'pa view',
                                   'ap view',
                                   'posteroanterior',
                                   'anteroposterior',
                                   'mri chest',
                                   'chest mri',
                                   'magnetic resonance',
                                   'pet scan',
                                   'pet-ct',
                                   'fdg',
                                   'ultrasound',
                                   'echocardiograph',
                                   'sonograph',
                                   'bronchoscop',
                                   'endoscop',
                                   'mammogr',
                                   'mammogram',
                                   'histopath',
                                   'h&e',
                                   'hematoxylin',
                                   'microscop',
                                   'intraoperative',
                                   'flowchart',
                                   'flow chart',
                                   'flow-chart',
                                   ' diagram',
                                   'schematic',
                                   'algorithm',
                                   'study design',
                                   'protocol',
                                   'workflow',
                                   ' table ',
                                   'timeline',
                                   ' bar graph',
                                   'bar chart',
                                   ' pie chart'],
              'imaging_modality': 'CT',
              'include_keywords': ['ct chest',
                                   'chest ct',
                                   'ct thorax',
                                   'thoracic ct',
                                   'computed tomography chest',
                                   'computed tomography of the chest',
                                   'chest computed tomography',
                                   'ct of the chest',
                                   'ct of chest',
                                   'ct scan of the chest',
                                   'ct scan chest',
                                   'chest ct scan',
                                   'ct pulmonary',
                                   'hrct chest',
                                   'hrct lung',
                                   'hrct of the lung',
                                   'high-resolution ct',
                                   'high resolution ct',
                                   'ctpa',
                                   'ct pulmonary angiograph',
                                   'low-dose ct',
                                   'ldct chest',
                                   'thorax ct',
                                   'ct thoracic',
                                   'contrast-enhanced ct chest',
                                   'contrast enhanced ct chest',
                                   'non-contrast ct chest',
                                   'noncontrast ct chest',
                                   'ct scan of thorax',
                                   'ct of thorax'],
              'llm_system_prompt': 'You are a radiology data curator specializing in chest CT. Extract structured '
                                   'information from chest CT case report text.\n'
                                   'Return ONLY valid JSON with these exact fields:\n'
                                   '{\n'
                                   '  "finding": "primary CT chest finding (e.g. \'right lower lobe consolidation with '
                                   "air bronchograms', 'bilateral ground-glass opacities', 'saddle pulmonary embolism "
                                   "at main pulmonary artery bifurcation', 'left pleural effusion with mediastinal "
                                   'shift\', \'spiculated right upper lobe nodule\')",\n'
                                   '  "diagnosis": "final clinical diagnosis (e.g. \'pulmonary embolism\', '
                                   "'community-acquired pneumonia', 'lung adenocarcinoma', 'COVID-19 pneumonia', "
                                   '\'idiopathic pulmonary fibrosis\')",\n'
                                   '  "laterality": "right | left | bilateral | central | mediastinal | N/A"\n'
                                   '}\n'
                                   '\n'
                                   'CRITICAL - Extraction priority:\n'
                                   '1. PRIMARY SOURCE: Use "Figure legend" and "Results text" as the PRIMARY source '
                                   'for finding extraction\n'
                                   '2. Extract CT chest-specific findings: density (GGO, consolidation, nodule, mass, '
                                   'atelectasis), distribution (lobar, segmental, diffuse, subpleural), enhancement '
                                   'pattern, vascular findings for CTPA\n'
                                   '3. Only use "Case presentation" for additional clinical context\n'
                                   '\n'
                                   'CRITICAL - Diagnosis normalization:\n'
                                   '- "Pulmonary embolism" NOT "PE" or "pulmonary thromboembolism"\n'
                                   '- "COVID-19 pneumonia" NOT "SARS-CoV-2 pneumonia"\n'
                                   '- "Tuberculosis" NOT "TB" or "pulmonary TB"\n'
                                   '- "Idiopathic pulmonary fibrosis" NOT "IPF"\n'
                                   '- "Non-small cell lung cancer" or specific subtype (lung adenocarcinoma, squamous '
                                   'cell carcinoma of lung)\n'
                                   '- "Sarcoidosis" NOT "sarcoid"\n'
                                   '- "Pneumocystis pneumonia" NOT "PCP"\n'
                                   '\n'
                                   'Laterality: right/left for lobar or unilateral findings | bilateral | central for '
                                   'trachea/main bronchus | mediastinal | N/A for diffuse ILD\n'
                                   '\n'
                                   "If uncertain, use 'unclear' or 'N/A'. Never return null.",
              'name': 'CT Chest',
              'search_keywords': ['CT chest',
                                  'chest CT',
                                  'chest computed tomography',
                                  'computed tomography chest',
                                  'HRCT chest',
                                  'high-resolution CT',
                                  'CT pulmonary',
                                  'CT thorax',
                                  'thoracic CT',
                                  'CTPA',
                                  'CT pulmonary angiography',
                                  'low-dose CT chest']},
 'CXR': {'anatomy': 'chest',
         'diagnosis_normalization': {'dextrocardia': 'Dextrocardia',
                                     'pneumocystis': 'Pneumocystis pneumonia',
                                     'schwannoma': 'Schwannoma'},
         'exclude_keywords': ['computed tomography',
                              ' ct ',
                              'ct scan',
                              'ct chest',
                              'mri',
                              'magnetic resonance',
                              'pet scan',
                              'fdg',
                              'fluorodeoxyglucose',
                              'ultrasound',
                              'echocardiograph',
                              'sonograph',
                              'bronchoscop',
                              'endoscop',
                              'histopath',
                              'h&e',
                              'hematoxylin',
                              'microscop',
                              'patholog',
                              'intraoperative',
                              'angiograph',
                              'fluoroscop',
                              'mammogr',
                              'mammogram',
                              'tomosynthesis',
                              ' dbt ',
                              'craniocaudal',
                              'mediolateral',
                              ' mlo ',
                              ' cc view',
                              'breast imag',
                              'flowchart',
                              'flow chart',
                              'flow-chart',
                              ' diagram',
                              'schematic',
                              'algorithm',
                              'study design',
                              'protocol',
                              'workflow',
                              ' table ',
                              'timeline',
                              'time course',
                              'time line',
                              'perioperative',
                              'postoperative course',
                              ' bar graph',
                              'bar chart',
                              ' pie chart',
                              'x-ray aspect'],
         'imaging_modality': 'XR',
         'include_keywords': ['chest x-ray',
                              'chest x ray',
                              'chest radiograph',
                              'cxr',
                              'plain chest',
                              'chest film',
                              'pa view',
                              'ap view',
                              'posteroanterior',
                              'anteroposterior',
                              'plain radiograph'],
         'llm_system_prompt': 'You are a radiology data curator. Extract structured information from chest X-ray case '
                              'report text.\n'
                              'Return ONLY valid JSON with these exact fields:\n'
                              '{\n'
                              '  "finding": "primary radiological finding (e.g. \'right lower lobe consolidation\')",\n'
                              '  "diagnosis": "final clinical diagnosis (e.g. \'community-acquired pneumonia\')",\n'
                              '  "laterality": "right | left | bilateral | central | N/A"\n'
                              '}\n'
                              '\n'
                              'CRITICAL - Extraction priority:\n'
                              '1. PRIMARY SOURCE: Use "Figure legend" and "Results text" as the PRIMARY source for '
                              'finding extraction\n'
                              '2. If the figure legend explicitly describes findings (e.g., "showed consolidation"), '
                              'extract from there\n'
                              '3. Only use "Case presentation" for additional context, NOT as primary source\n'
                              '4. For articles with multiple figures, focus ONLY on the specific figure being '
                              'analyzed\n'
                              '\n'
                              'CRITICAL - Diagnosis normalization:\n'
                              '1. Use standardized medical terminology (UMLS/MeSH)\n'
                              '2. Sentence case (capitalize first word only, except proper nouns)\n'
                              '3. Concise canonical form\n'
                              '4. If matching an author keyword, use that exact capitalization\n'
                              '\n'
                              'Examples:\n'
                              '- "Schwannoma" NOT "schwannoma of recurrent laryngeal nerve"\n'
                              '- "Pneumocystis pneumonia" NOT "Pneumocystis jirovecii pneumonia"\n'
                              '\n'
                              "If uncertain, use 'unclear' or 'N/A'. Never return null.",
         'name': 'Chest X-ray',
         'search_keywords': ['chest radiograph',
                             'chest X-ray',
                             'chest x-ray',
                             'chest x ray',
                             'CXR',
                             'plain chest film',
                             'chest roentgenogram',
                             'posteroanterior']},
 'MAMMOGRAM': {'anatomy': 'breast',
               'diagnosis_normalization': {'dcis': 'Ductal carcinoma in situ',
                                           'fibroadenoma': 'Fibroadenoma',
                                           'idc': 'Invasive ductal carcinoma',
                                           'ilc': 'Invasive lobular carcinoma',
                                           'phyllodes': 'Phyllodes tumor'},
               'exclude_keywords': ['breast ultrasound',
                                    'breast us',
                                    'sonogra',
                                    'breast mri',
                                    'magnetic resonance',
                                    ' ct ',
                                    'computed tomography',
                                    'chest x-ray',
                                    'chest xray',
                                    'chest radiograph',
                                    ' cxr ',
                                    'chest film',
                                    'posteroanterior',
                                    'anteroposterior',
                                    'pa view',
                                    'ap view',
                                    ' lung ',
                                    ' pulmonary ',
                                    'biopsy',
                                    'histopath',
                                    'microscop',
                                    'patholog',
                                    'h&e',
                                    'hematoxylin',
                                    'needle localization',
                                    'wire localization',
                                    'stereotactic biopsy',
                                    'core biopsy',
                                    'flowchart',
                                    'flow chart',
                                    ' diagram',
                                    'schematic',
                                    'algorithm',
                                    ' table ',
                                    'timeline',
                                    'workflow'],
               'imaging_modality': 'MG',
               'include_keywords': ['mammogr',
                                    'mammogram',
                                    'breast imag',
                                    'breast radiograph',
                                    'craniocaudal',
                                    'mediolateral oblique',
                                    ' mlo ',
                                    ' cc view',
                                    ' ml view',
                                    'tomosynthesis',
                                    ' dbt ',
                                    'screening mammogram',
                                    'diagnostic mammogram',
                                    'bilateral mammogr',
                                    'unilateral mammogr',
                                    'spot compression',
                                    'magnification view',
                                    ' rmlo ',
                                    ' rcc ',
                                    ' lmlo ',
                                    ' lcc ',
                                    'breast x-ray',
                                    'breast radiolog',
                                    'bi-rads',
                                    'birads',
                                    'microcalcification',
                                    'macrocalcification',
                                    'architectural distortion',
                                    'breast density',
                                    'fibroglandular'],
               'llm_system_prompt': (
                                    'You are a radiology data curator. Extract structured information from mammography case report text.\n'
                                    'Return ONLY valid JSON with these exact fields:\n'
                                    '{\n'
                                    '  "finding": "primary radiological finding (e.g. \'irregular mass with calcifications\')",\n'
                                    '  "diagnosis": "final clinical diagnosis (e.g. \'invasive ductal carcinoma\')",\n'
                                    '  "laterality": "right | left | bilateral | N/A"\n'
                                    '}\n\n'
                                    '*** STRICT SCOPE RULE — THIS SPECIFIC FIGURE ONLY ***\n'
                                    'You are extracting information for ONE specific figure (identified by Figure legend).\n'
                                    'ONLY use findings explicitly described in the "Figure legend" field.\n'
                                    'Use "Results text", "Case presentation", and "Abstract" ONLY to identify the final diagnosis — never to add findings from other figures or other imaging modalities.\n'
                                    'DO NOT include findings from: other figures in the same paper, other imaging modalities (ultrasound, MRI, CT), different time points (pre-op vs post-op, before vs after treatment).\n'
                                    'If the figure legend does not describe a mammographic finding, write "unclear" for finding.\n\n'
                                    'CRITICAL - Diagnosis normalization:\n'
                                    '1. Use standardized breast pathology terminology\n'
                                    '2. Sentence case (capitalize first word, proper nouns)\n'
                                    '3. Concise canonical form\n\n'
                                    'Examples:\n'
                                    '- "Invasive ductal carcinoma" NOT "invasive ductal carcinoma of left breast"\n'
                                    '- "Fibroadenoma" NOT "benign fibroadenoma"\n\n'
                                    "If uncertain, use 'unclear' or 'N/A'. Never return null."
                                    ),
               'name': 'Mammogram',
               'search_keywords': ['mammogram',
                                   'mammography',
                                   'breast imaging',
                                   'digital breast tomosynthesis',
                                   'DBT',
                                   'screening mammogram',
                                   'diagnostic mammogram']},
 'MRI_BRAIN': {'anatomy': 'brain',
               'diagnosis_normalization': {' avm ': 'Arteriovenous malformation',
                                           ' cva ': 'Acute ischemic stroke',
                                           ' gbm ': 'Glioblastoma',
                                           ' ms ': 'Multiple sclerosis',
                                           ' pml ': 'Progressive multifocal leukoencephalopathy',
                                           ' pres ': 'Posterior reversible encephalopathy syndrome',
                                           'acoustic neuroma': 'Vestibular schwannoma',
                                           'acute ischemic stroke': 'Acute ischemic stroke',
                                           'arteriovenous malformation': 'Arteriovenous malformation',
                                           'brain metastasis': 'Brain metastasis',
                                           'cavernoma': 'Cavernous malformation',
                                           'cavernous malformation': 'Cavernous malformation',
                                           'cerebral cavernous': 'Cavernous malformation',
                                           'cerebral infarct': 'Acute ischemic stroke',
                                           'cerebral infarction': 'Acute ischemic stroke',
                                           'cerebral metastasis': 'Brain metastasis',
                                           'craniopharyngioma': 'Craniopharyngioma',
                                           'ependymoma': 'Ependymoma',
                                           'glioblastoma': 'Glioblastoma',
                                           'glioblastoma multiforme': 'Glioblastoma',
                                           'medulloblastoma': 'Medulloblastoma',
                                           'meningioma': 'Meningioma',
                                           'metastasis': 'Brain metastasis',
                                           'multiple sclerosis': 'Multiple sclerosis',
                                           'neurocysticercosis': 'Neurocysticercosis',
                                           'pituitary adenoma': 'Pituitary adenoma',
                                           'posterior reversible encephalopathy': 'Posterior reversible encephalopathy '
                                                                                  'syndrome',
                                           'progressive multifocal leukoencephalopathy': 'Progressive multifocal '
                                                                                         'leukoencephalopathy',
                                           'vestibular schwannoma': 'Vestibular schwannoma'},
               'exclude_keywords': ['spine mri',
                                    'mri spine',
                                    'spinal mri',
                                    'spinal cord mri',
                                    'lumbar mri',
                                    'cervical spine mri',
                                    'thoracic spine mri',
                                    'mri lumbar',
                                    'mri cervical spine',
                                    'mri abdomen',
                                    'abdominal mri',
                                    'liver mri',
                                    'mrcp',
                                    'mri pelvis',
                                    'pelvic mri',
                                    'prostate mri',
                                    'pi-rads',
                                    'pirads',
                                    'neck mri',
                                    'mri neck',
                                    'parotid mri',
                                    'thyroid mri',
                                    'breast mri',
                                    'mri breast',
                                    'cardiac mri',
                                    'heart mri',
                                    'knee mri',
                                    'shoulder mri',
                                    'hip mri',
                                    'stir',
                                    'ct brain',
                                    'brain ct',
                                    'ct head',
                                    'head ct',
                                    'computed tomography brain',
                                    'ncct brain',
                                    'pet scan',
                                    'fdg',
                                    'spect',
                                    'ultrasound',
                                    'sonograph',
                                    'echocardiograph',
                                    'fluoroscop',
                                    'x-ray',
                                    'radiograph',
                                    'mammogr',
                                    'mammogram',
                                    'histopath',
                                    'h&e',
                                    'hematoxylin',
                                    'microscop',
                                    'flowchart',
                                    'flow chart',
                                    'flow-chart',
                                    ' diagram',
                                    'schematic',
                                    'algorithm',
                                    'study design',
                                    'protocol',
                                    'workflow',
                                    ' table ',
                                    'bar graph',
                                    'bar chart',
                                    'pie chart'],
               'imaging_modality': 'MR',
               'include_keywords': ['mri brain',
                                    'mri of the brain',
                                    'mri of brain',
                                    'brain mri',
                                    'cerebral mri',
                                    'cranial mri',
                                    'intracranial mri',
                                    'brain mr imaging',
                                    'brain mr image',
                                    'brain magnetic resonance',
                                    'cerebral magnetic resonance',
                                    'mra brain',
                                    'mra of the brain',
                                    'brain mra',
                                    'intracranial mra',
                                    'intracranial mr angiograph',
                                    'mr venograph',
                                    'mrv brain',
                                    'flair',
                                    ' swi ',
                                    'swi sequence',
                                    'susceptibility-weighted',
                                    'susceptibility weighted',
                                    'dwi brain',
                                    'diffusion brain',
                                    'diffusion-weighted brain',
                                    'adc map brain',
                                    'apparent diffusion brain',
                                    'mri cerebellum',
                                    'mri brainstem',
                                    'mri temporal lobe',
                                    'mri frontal lobe',
                                    'mri hippocampus',
                                    'mri basal ganglia',
                                    'mri thalamus',
                                    'mri corpus callosum',
                                    'mri ventricle',
                                    'mri white matter',
                                    'pituitary mri',
                                    'sellar mri',
                                    'mri pituitary',
                                    'acoustic neuroma mri',
                                    'vestibular schwannoma mri'],
               'llm_system_prompt': 'You are a radiology data curator specializing in brain MRI. Extract structured '
                                    'information from brain MRI case report text.\n'
                                    'Return ONLY valid JSON with these exact fields:\n'
                                    '{\n'
                                    '  "finding": "primary MRI finding with signal characteristics (e.g. \'T2/FLAIR '
                                    'hyperintense lesion in right temporal lobe with restricted diffusion and ring '
                                    "enhancement', 'T1 hyperintense acute subdural collection along left convexity', "
                                    "'DWI restriction in left MCA territory with corresponding ADC "
                                    'hypointensity\')",\n'
                                    '  "diagnosis": "final clinical diagnosis (e.g. \'glioblastoma\', \'acute ischemic '
                                    'stroke\', \'multiple sclerosis\', \'cavernous malformation\')",\n'
                                    '  "laterality": "right | left | bilateral | midline | N/A"\n'
                                    '}\n'
                                    '\n'
                                    'CRITICAL - MRI signal terminology (include in finding field):\n'
                                    '- T1: hyperintense (fat, subacute blood, melanin, proteinaceous) or hypointense '
                                    '(edema, most lesions)\n'
                                    '- T2/FLAIR: hyperintense (edema, demyelination, gliosis, most pathology) or '
                                    'hypointense (iron, calcium, fibrous)\n'
                                    '- DWI/ADC: diffusion restriction = bright DWI + dark ADC (acute infarct, '
                                    'hypercellular tumor, abscess)\n'
                                    '- Enhancement: ring-enhancing (GBM, abscess, mets), leptomeningeal, homogeneous\n'
                                    '- SWI: blooming artifact (hemorrhage, calcification, cavernoma)\n'
                                    '\n'
                                    'CRITICAL - Diagnosis normalization:\n'
                                    '- "Glioblastoma" NOT "GBM" or "glioblastoma multiforme"\n'
                                    '- "Acute ischemic stroke" NOT "CVA" or "cerebral infarction"\n'
                                    '- "Multiple sclerosis" NOT "MS plaque"\n'
                                    '- "Cavernous malformation" NOT "cavernoma"\n'
                                    '- "Vestibular schwannoma" NOT "acoustic neuroma"\n'
                                    '- "Posterior reversible encephalopathy syndrome" NOT "PRES"\n'
                                    '- "Progressive multifocal leukoencephalopathy" NOT "PML"\n'
                                    '\n'
                                    'Laterality: right/left for hemispheric lesions | bilateral | midline (corpus '
                                    'callosum, vermis, brainstem, pineal) | N/A for diffuse processes\n'
                                    '\n'
                                    "If uncertain, use 'unclear' or 'N/A'. Never return null.",
               'name': 'Brain MRI',
               'search_keywords': ['brain MRI',
                                   'MRI brain',
                                   'cerebral MRI',
                                   'brain magnetic resonance',
                                   'cerebral magnetic resonance imaging',
                                   'MRA brain',
                                   'brain MR angiography',
                                   'diffusion weighted imaging brain',
                                   'FLAIR brain',
                                   'brain MR imaging',
                                   'intracranial MRI',
                                   'cranial MRI']},
 'MRI_SPINE': {'anatomy': 'spine',
               'diagnosis_normalization': {' csm ': 'Cervical spondylotic myelopathy',
                                           ' opll ': 'Ossification of posterior longitudinal ligament',
                                           'astrocytoma': 'Spinal cord astrocytoma',
                                           'cervical disc': 'Cervical disc herniation',
                                           'cervical spinal stenosis': 'Cervical spinal stenosis',
                                           'chiari': 'Chiari malformation',
                                           'disc extrusion': 'Disc herniation',
                                           'disc herniation': 'Disc herniation',
                                           'disc protrusion': 'Disc herniation',
                                           'ependymoma': 'Spinal ependymoma',
                                           'epidural abscess': 'Spinal epidural abscess',
                                           'hemangioma': 'Vertebral hemangioma',
                                           'lumbar disc': 'Lumbar disc herniation',
                                           'lumbar spinal stenosis': 'Lumbar spinal stenosis',
                                           'ossification of posterior longitudinal ligament': 'Ossification of '
                                                                                              'posterior longitudinal '
                                                                                              'ligament',
                                           'spinal cord infarct': 'Spinal cord infarction',
                                           'spinal epidural abscess': 'Spinal epidural abscess',
                                           'spinal meningioma': 'Spinal meningioma',
                                           'spinal metastases': 'Spinal metastasis',
                                           'spinal metastasis': 'Spinal metastasis',
                                           'spinal stenosis': 'Spinal stenosis',
                                           'spondylodiscitis': 'Spondylodiscitis',
                                           'spondylolisthesis': 'Spondylolisthesis',
                                           'spondylotic myelopathy': 'Cervical spondylotic myelopathy',
                                           'syringomyelia': 'Syringomyelia',
                                           'syrinx': 'Syringomyelia',
                                           'transverse myelitis': 'Transverse myelitis',
                                           'vertebral hemangioma': 'Vertebral hemangioma',
                                           'vertebral osteomyelitis': 'Vertebral osteomyelitis'},
               'exclude_keywords': ['mri brain',
                                    'brain mri',
                                    'cerebral mri',
                                    'cranial mri',
                                    'flair',
                                    ' swi ',
                                    'swi sequence',
                                    'susceptibility-weighted',
                                    'susceptibility weighted',
                                    'dwi brain',
                                    'diffusion brain',
                                    'neck mri',
                                    'mri neck',
                                    'soft tissue neck mri',
                                    'parotid mri',
                                    'thyroid mri',
                                    'carotid mri',
                                    'mri abdomen',
                                    'abdominal mri',
                                    'liver mri',
                                    'mrcp',
                                    'mri pelvis',
                                    'pelvic mri',
                                    'prostate mri',
                                    'pi-rads',
                                    'pirads',
                                    'breast mri',
                                    'mri breast',
                                    'cardiac mri',
                                    'heart mri',
                                    'knee mri',
                                    'shoulder mri',
                                    'hip mri',
                                    'ct spine',
                                    'spine ct',
                                    'computed tomography spine',
                                    'ct lumbar',
                                    'ct cervical spine',
                                    'ct thoracic spine',
                                    'ct myelograph',
                                    'pet scan',
                                    'fdg',
                                    'ultrasound',
                                    'sonograph',
                                    'x-ray',
                                    'radiograph',
                                    'plain film',
                                    'fluoroscop',
                                    'histopath',
                                    'h&e',
                                    'hematoxylin',
                                    'microscop',
                                    'flowchart',
                                    'flow chart',
                                    'flow-chart',
                                    ' diagram',
                                    'schematic',
                                    'algorithm',
                                    'study design',
                                    'protocol',
                                    'workflow',
                                    ' table ',
                                    'bar graph',
                                    'bar chart',
                                    'pie chart'],
               'imaging_modality': 'MR',
               'include_keywords': ['lumbar mri',
                                    'mri lumbar',
                                    'mri of the lumbar',
                                    'lumbar spine mri',
                                    'mri lumbar spine',
                                    'lumbosacral mri',
                                    'mri lumbosacral',
                                    'cervical spine mri',
                                    'mri cervical spine',
                                    'mri of the cervical spine',
                                    'cervical spine magnetic resonance',
                                    'thoracic spine mri',
                                    'mri thoracic spine',
                                    'mri of the thoracic spine',
                                    'spine mri',
                                    'mri spine',
                                    'spinal mri',
                                    'mri of the spine',
                                    'spinal cord mri',
                                    'mri spinal cord',
                                    'mri of the spinal cord',
                                    'vertebral mri',
                                    'mri vertebra',
                                    'mri intervertebral',
                                    'disc mri',
                                    'mri disc',
                                    'intervertebral disc mri',
                                    'mri herniation',
                                    'disc herniation mri',
                                    'mri conus',
                                    'mri cauda equina',
                                    'mri sacrum',
                                    'mri epidural',
                                    'epidural mri',
                                    'stir'],
               'llm_system_prompt': (
                                    'You are a radiology data curator specializing in spine MRI. Extract structured information from spine MRI case report text.\n'
                                    'Return ONLY valid JSON with these exact fields:\n'
                                    '{\n'
                                    '  "finding": "primary MRI finding with signal characteristics and spinal level (e.g. \'T2 hyperintense lesion at C5-C6 with cord edema and contrast enhancement\')",\n'
                                    '  "diagnosis": "final clinical diagnosis (e.g. \'cervical disc herniation with myelopathy\')",\n'
                                    '  "laterality": "right | left | bilateral | central | N/A"\n'
                                    '}\n\n'
                                    '*** STRICT SCOPE RULE — THIS SPECIFIC FIGURE ONLY ***\n'
                                    'You are extracting information for ONE specific figure (identified by Figure legend).\n'
                                    'ONLY use findings explicitly described in the "Figure legend" field.\n'
                                    'Use "Results text", "Case presentation", and "Abstract" ONLY to identify the final diagnosis — never to add findings from other figures or time points.\n'
                                    'DO NOT include findings from: other figures in the same paper, other imaging modalities (CT, X-ray), different time points (pre-treatment vs post-treatment, follow-up vs initial presentation).\n'
                                    'If this figure shows a follow-up/post-treatment scan, describe ONLY what is visible in this follow-up image — do not mix in initial presentation findings.\n'
                                    'If the figure legend does not describe a spine MRI finding, write "unclear" for finding.\n\n'
                                    'CRITICAL - MRI signal terminology for spine (include in finding field):\n'
                                    '- T1: hypointense (disc herniation, edema), hyperintense (fat, subacute blood, lipoma)\n'
                                    '- T2: hyperintense (cord edema, disc herniation, tumor, infection), hypointense (sclerosis, fibrous)\n'
                                    '- STIR: hyperintense (marrow edema, infection, inflammation, fracture)\n'
                                    '- Enhancement: confirms active infection, tumor, demyelination\n'
                                    '- Include spinal level in finding (e.g., L4-L5, C5-C6, T10-T11)\n\n'
                                    'CRITICAL - Diagnosis normalization:\n'
                                    '- Specify region: "Lumbar disc herniation" / "Cervical disc herniation"\n'
                                    '- "Cervical spondylotic myelopathy" NOT "CSM"\n'
                                    '- "Spinal metastasis" NOT "spinal mets"\n'
                                    '- "Spondylodiscitis" (add pathogen if known: tuberculous/pyogenic)\n\n'
                                    'Laterality: right/left for foraminal/paraspinal | bilateral | central for canal/central cord | N/A for vertebral body or multilevel\n\n'
                                    "If uncertain, use 'unclear' or 'N/A'. Never return null."
                                    ),
               'name': 'Spine MRI',
               'search_keywords': ['spine MRI',
                                   'spinal MRI',
                                   'lumbar MRI',
                                   'cervical spine MRI',
                                   'thoracic spine MRI',
                                   'MRI lumbar spine',
                                   'MRI cervical spine',
                                   'spinal cord MRI',
                                   'vertebral MRI',
                                   'lumbosacral MRI']},
 'US_ABDOMEN': {'anatomy': 'abdomen',
                'diagnosis_normalization': {' cbd stone': 'Choledocholithiasis',
                                            ' hcc ': 'Hepatocellular carcinoma',
                                            ' rcc ': 'Renal cell carcinoma',
                                            'acute cholecystitis': 'Acute cholecystitis',
                                            'cholecystitis': 'Acute cholecystitis',
                                            'choledocholithiasis': 'Choledocholithiasis',
                                            'cholelithiasis': 'Cholelithiasis',
                                            'common bile duct stone': 'Choledocholithiasis',
                                            'fatty liver': 'Hepatic steatosis',
                                            'gallstone': 'Cholelithiasis',
                                            'gallstones': 'Cholelithiasis',
                                            'hepatic abscess': 'Hepatic abscess',
                                            'hepatic hemangioma': 'Hepatic hemangioma',
                                            'hepatic steatosis': 'Hepatic steatosis',
                                            'hepatocellular carcinoma': 'Hepatocellular carcinoma',
                                            'hydronephrosis': 'Hydronephrosis',
                                            'kidney stone': 'Nephrolithiasis',
                                            'liver hemangioma': 'Hepatic hemangioma',
                                            'nephrolithiasis': 'Nephrolithiasis',
                                            'pyogenic liver abscess': 'Hepatic abscess',
                                            'renal calculus': 'Nephrolithiasis',
                                            'renal cell carcinoma': 'Renal cell carcinoma',
                                            'splenic infarct': 'Splenic infarct',
                                            'splenic infarction': 'Splenic infarct'},
                'exclude_keywords': ['ct abdomen',
                                     'abdominal ct',
                                     'computed tomography abdomen',
                                     'ct scan abdomen',
                                     'ct of the abdomen',
                                     'cect abdomen',
                                     'contrast-enhanced ct',
                                     'portal venous phase',
                                     'mri abdomen',
                                     'abdominal mri',
                                     'magnetic resonance abdomen',
                                     'liver mri',
                                     'mrcp',
                                     'magnetic resonance cholangiopancreatography',
                                     'abdominal x-ray',
                                     'plain abdominal',
                                     'kub radiograph',
                                     'abdominal radiograph',
                                     'pet scan',
                                     'pet-ct',
                                     'fdg',
                                     'spect',
                                     'obstetric ultrasound',
                                     'fetal ultrasound',
                                     'transvaginal ultrasound',
                                     'breast ultrasound',
                                     'breast us',
                                     'breast sonography',
                                     'thyroid ultrasound',
                                     'thyroid us',
                                     'ti-rads',
                                     'carotid ultrasound',
                                     'carotid doppler',
                                     'vascular ultrasound',
                                     'transrectal ultrasound',
                                     'trus',
                                     'prostate ultrasound',
                                     'pelvic ultrasound',
                                     'transvaginal',
                                     'endovaginal',
                                     'echocardiograph',
                                     'cardiac ultrasound',
                                     'transthoracic echo',
                                     'transesophageal echo',
                                     ' tee ',
                                     ' tte ',
                                     'endoscopic ultrasound',
                                     ' eus ',
                                     'endosonography',
                                     'histopath',
                                     'h&e',
                                     'hematoxylin',
                                     'microscop',
                                     'flowchart',
                                     'flow chart',
                                     ' diagram',
                                     'schematic',
                                     'algorithm',
                                     'study design',
                                     ' table ',
                                     'bar graph'],
                'imaging_modality': 'US',
                'include_keywords': ['abdominal ultrasound',
                                     'ultrasound abdomen',
                                     'abdominal sonography',
                                     'abdominal us',
                                     'us abdomen',
                                     'sonography abdomen',
                                     'upper abdominal ultrasound',
                                     'upper abdominal sonography',
                                     'hepatic ultrasound',
                                     'liver ultrasound',
                                     'ultrasound liver',
                                     'hepatic sonography',
                                     'us liver',
                                     'liver sonogram',
                                     'gallbladder ultrasound',
                                     'ultrasound gallbladder',
                                     'biliary ultrasound',
                                     'choledochal ultrasound',
                                     'renal ultrasound',
                                     'kidney ultrasound',
                                     'ultrasound kidney',
                                     'renal sonography',
                                     'us kidney',
                                     'kidney sonogram',
                                     'splenic ultrasound',
                                     'spleen ultrasound',
                                     'pancreatic ultrasound',
                                     'hyperechoic',
                                     'hypoechoic',
                                     'anechoic',
                                     'isoechoic',
                                     'heterogeneous echogenicity',
                                     'acoustic shadow'],
                'llm_system_prompt': 'You are a radiology data curator specializing in abdominal ultrasound. Extract '
                                     'structured information from abdominal ultrasound case report text.\n'
                                     'Return ONLY valid JSON with these exact fields:\n'
                                     '{\n'
                                     '  "finding": "primary ultrasound finding with echogenicity (e.g. \'hyperechoic '
                                     "mass in right hepatic lobe with posterior acoustic shadowing', 'hypoechoic "
                                     "lesion in left kidney with increased vascularity on color Doppler', 'dilated "
                                     'common bile duct measuring 9mm with echogenic stone\')",\n'
                                     '  "diagnosis": "final clinical diagnosis (e.g. \'hepatocellular carcinoma\', '
                                     '\'acute cholecystitis\', \'nephrolithiasis\', \'renal cell carcinoma\')",\n'
                                     '  "laterality": "right | left | bilateral | midline | N/A"\n'
                                     '}\n'
                                     '\n'
                                     'CRITICAL - Ultrasound echogenicity terminology (include in finding field):\n'
                                     '- Hyperechoic: bright/echogenic (calculi, fat, fibrosis, gas)\n'
                                     '- Hypoechoic: dark/low echogenicity (solid masses, fluid collections, '
                                     'hematomas)\n'
                                     '- Anechoic: black/no internal echoes (simple cysts, ascites, bile, urine)\n'
                                     '- Isoechoic: similar echogenicity to surrounding parenchyma\n'
                                     '- Heterogeneous: mixed echogenicity pattern\n'
                                     '- Acoustic shadowing: posterior shadowing (stones, calcifications, gas)\n'
                                     '- Posterior acoustic enhancement: increased through-transmission (cysts, fluid)\n'
                                     '- Color Doppler: vascularity assessment (increased in tumors, absent in cysts)\n'
                                     '\n'
                                     'CRITICAL - Extraction priority:\n'
                                     '1. PRIMARY SOURCE: Use "Figure legend" and "Results text" as PRIMARY source\n'
                                     '2. Extract: organ (liver, gallbladder, kidney, spleen, pancreas), echogenicity, '
                                     'size, Doppler findings\n'
                                     '3. Common findings: hepatic lesions, cholelithiasis/cholecystitis, '
                                     'hydronephrosis, renal masses, splenic lesions\n'
                                     '4. Only use "Case presentation" for additional context\n'
                                     '\n'
                                     'CRITICAL - Diagnosis normalization:\n'
                                     '- "Hepatocellular carcinoma" NOT "HCC"\n'
                                     '- "Acute cholecystitis" NOT just "cholecystitis"\n'
                                     '- "Nephrolithiasis" NOT "kidney stone"\n'
                                     '- "Renal cell carcinoma" NOT "RCC"\n'
                                     '- "Hepatic hemangioma" NOT "liver hemangioma"\n'
                                     '- "Choledocholithiasis" NOT "CBD stone"\n'
                                     '- "Hepatic steatosis" NOT "fatty liver"\n'
                                     '\n'
                                     'Laterality: right/left for liver lobes, kidneys, adrenals | bilateral | midline '
                                     'for gallbladder, CBD, pancreas, aorta | N/A for diffuse disease\n'
                                     '\n'
                                     "If uncertain, use 'unclear' or 'N/A'. Never return null.",
                'name': 'Abdominal Ultrasound',
                'search_keywords': ['abdominal ultrasound',
                                    'ultrasound abdomen',
                                    'abdominal sonography',
                                    'hepatic ultrasound',
                                    'liver ultrasound',
                                    'renal ultrasound',
                                    'ultrasound liver',
                                    'ultrasound kidney',
                                    'abdominal US',
                                    'upper abdominal ultrasound']},
 'US_PELVIS': {'anatomy': 'pelvis',
               'diagnosis_normalization': {' bph ': 'Benign prostatic hyperplasia',
                                           ' myoma ': 'Uterine fibroid',
                                           'adenomyosis': 'Adenomyosis',
                                           'benign prostatic hyperplasia': 'Benign prostatic hyperplasia',
                                           'ectopic pregnancy': 'Ectopic pregnancy',
                                           'endometrioma': 'Endometrioma',
                                           'endometriosis': 'Endometriosis',
                                           'leiomyoma': 'Uterine fibroid',
                                           'ovarian cyst': 'Ovarian cyst',
                                           'ovarian cystadenoma': 'Ovarian cystadenoma',
                                           'ovarian torsion': 'Ovarian torsion',
                                           'prostate cancer': 'Prostate cancer',
                                           'prostate carcinoma': 'Prostate cancer',
                                           'prostatic carcinoma': 'Prostate cancer',
                                           'uterine fibroid': 'Uterine fibroid'},
               'exclude_keywords': ['obstetric ultrasound',
                                    'fetal ultrasound',
                                    'pregnancy ultrasound',
                                    'gestational sac',
                                    'fetal pole',
                                    'fetal heart',
                                    ' bpd ',
                                    ' crl ',
                                    'amniotic fluid',
                                    'first trimester',
                                    'second trimester',
                                    'third trimester',
                                    'gravid',
                                    'pregnant',
                                    'ct pelvis',
                                    'pelvic ct',
                                    'computed tomography pelvis',
                                    'mri pelvis',
                                    'pelvic mri',
                                    'magnetic resonance pelvis',
                                    ' pi-rads ',
                                    'pirads',
                                    'abdominal ultrasound',
                                    'hepatic ultrasound',
                                    'renal ultrasound',
                                    'breast ultrasound',
                                    'breast us',
                                    'thyroid ultrasound',
                                    'thyroid us',
                                    'carotid ultrasound',
                                    'vascular ultrasound',
                                    'echocardiograph',
                                    'cardiac ultrasound',
                                    'histopath',
                                    'h&e',
                                    'microscop',
                                    'hysteroscopy',
                                    'laparoscopy',
                                    'colposcopy',
                                    'flowchart',
                                    ' diagram',
                                    'schematic',
                                    ' table '],
               'imaging_modality': 'US',
               'include_keywords': ['pelvic ultrasound',
                                    'ultrasound pelvis',
                                    'pelvic sonography',
                                    'pelvic us',
                                    'us pelvis',
                                    'pelvic sonogram',
                                    'transvaginal ultrasound',
                                    'transvaginal sonography',
                                    'endovaginal ultrasound',
                                    'tvs',
                                    'tv ultrasound',
                                    'transrectal ultrasound',
                                    'trus',
                                    'prostate ultrasound',
                                    'ultrasound prostate',
                                    'uterine ultrasound',
                                    'uterus ultrasound',
                                    'ultrasound uterus',
                                    'ovarian ultrasound',
                                    'ovary ultrasound',
                                    'adnexal ultrasound',
                                    'endometrial thickness',
                                    'endometrium ultrasound',
                                    'ovarian cyst',
                                    'endometriosis',
                                    'uterine fibroid',
                                    'adenomyosis',
                                    'endometrioma'],
               'llm_system_prompt': (
                                    'You are a radiology data curator specializing in pelvic ultrasound. Extract structured information from pelvic ultrasound case report text.\n'
                                    'Return ONLY valid JSON with these exact fields:\n'
                                    '{\n'
                                    '  "finding": "primary pelvic finding (e.g. \'complex cystic mass in right ovary measuring 6 cm with internal septations\')",\n'
                                    '  "diagnosis": "final diagnosis (e.g. \'ovarian cyst\', \'endometriosis\', \'uterine fibroid\')",\n'
                                    '  "laterality": "right | left | bilateral | midline | N/A"\n'
                                    '}\n\n'
                                    '*** STRICT SCOPE RULE — THIS SPECIFIC FIGURE ONLY ***\n'
                                    'You are extracting information for ONE specific figure (identified by Figure legend).\n'
                                    'ONLY use findings explicitly described in the "Figure legend" field.\n'
                                    'Use "Results text", "Case presentation", and "Abstract" ONLY to identify the final diagnosis — never to add findings from other figures.\n'
                                    'DO NOT include findings from: other figures in the same paper, other imaging modalities (CT, MRI, X-ray, laparoscopy), different time points.\n'
                                    'DO NOT mix findings from different ultrasound approaches (e.g., if this figure is transvaginal, do not include transabdominal findings from other figures).\n'
                                    'If the figure legend does not describe a pelvic ultrasound finding, write "unclear" for finding.\n\n'
                                    'CRITICAL - Pelvic ultrasound terminology (include in finding field):\n'
                                    '- Approach: transabdominal, transvaginal (TVS), transrectal (TRUS)\n'
                                    '- Uterus: endometrial thickness, fibroids, adenomyosis\n'
                                    '- Ovaries: simple vs complex cysts, solid masses, endometriomas (ground-glass echogenicity)\n'
                                    '- Vascularity: color Doppler assessment\n\n'
                                    'CRITICAL - Diagnosis normalization:\n'
                                    '- "Ovarian cyst" (specify type: simple, complex, endometrioma, dermoid)\n'
                                    '- "Uterine fibroid" NOT "leiomyoma" or "myoma"\n'
                                    '- "Endometriosis" (keep as is)\n'
                                    '- "Prostate cancer" NOT "prostate carcinoma"\n\n'
                                    'Laterality: right | left for ovaries, adnexa | bilateral | midline for uterus, prostate | N/A\n\n'
                                    "If uncertain, use 'unclear' or 'N/A'. Never return null."
                                    ),
               'name': 'Pelvic Ultrasound',
               'search_keywords': ['pelvic ultrasound',
                                   'ultrasound pelvis',
                                   'pelvic sonography',
                                   'transvaginal ultrasound',
                                   'transrectal ultrasound',
                                   'TRUS',
                                   'uterine ultrasound',
                                   'ovarian ultrasound',
                                   'prostate ultrasound',
                                   'endovaginal ultrasound',
                                   'pelvic US']},
 'US_VASCULAR': {'anatomy': 'vascular',
                 'diagnosis_normalization': {' aaa ': 'Abdominal aortic aneurysm',
                                             ' dvt ': 'Deep vein thrombosis',
                                             ' pad ': 'Peripheral arterial disease',
                                             ' pe ': 'Pulmonary embolism',
                                             'abdominal aortic aneurysm': 'Abdominal aortic aneurysm',
                                             'carotid artery stenosis': 'Carotid stenosis',
                                             'carotid stenosis': 'Carotid stenosis',
                                             'deep vein thrombosis': 'Deep vein thrombosis',
                                             'peripheral arterial disease': 'Peripheral arterial disease',
                                             'pulmonary embolism': 'Pulmonary embolism',
                                             'renal artery stenosis': 'Renal artery stenosis',
                                             'subclavian steal syndrome': 'Subclavian steal syndrome'},
                 'exclude_keywords': ['echocardiograph',
                                      'transthoracic echo',
                                      'transesophageal echo',
                                      ' tee ',
                                      ' tte ',
                                      'cardiac ultrasound',
                                      ' cta ',
                                      'ct angiography',
                                      'computed tomography angiography',
                                      ' mra ',
                                      'mr angiography',
                                      'magnetic resonance angiography',
                                      'ct aortogram',
                                      'mri aorta',
                                      'abdominal ultrasound',
                                      'hepatic ultrasound',
                                      'renal ultrasound',
                                      'obstetric ultrasound',
                                      'fetal ultrasound',
                                      'breast ultrasound',
                                      'breast us',
                                      'thyroid ultrasound',
                                      'thyroid us',
                                      'pelvic ultrasound',
                                      'transvaginal',
                                      'thyroid doppler',
                                      'liver doppler',
                                      'renal doppler',
                                      'testicular doppler',
                                      'scrotal doppler',
                                      'angiography',
                                      'catheter angiogram',
                                      'venography',
                                      'histopath',
                                      'microscop',
                                      'flowchart',
                                      ' diagram',
                                      'schematic',
                                      ' table '],
                 'imaging_modality': 'US',
                 'include_keywords': ['carotid ultrasound',
                                      'carotid doppler',
                                      'carotid duplex',
                                      'ultrasound carotid',
                                      'doppler carotid',
                                      'carotid sonography',
                                      'venous ultrasound',
                                      'venous doppler',
                                      'deep vein thrombosis',
                                      ' dvt ',
                                      'lower extremity doppler',
                                      'upper extremity doppler',
                                      'compression ultrasound',
                                      'arterial doppler',
                                      'arterial ultrasound',
                                      'peripheral arterial',
                                      'lower extremity arterial',
                                      'renal artery doppler',
                                      'spectral doppler',
                                      'color doppler',
                                      'power doppler',
                                      'peak systolic velocity',
                                      ' psv ',
                                      'end-diastolic velocity',
                                      'resistive index',
                                      ' ri ',
                                      'pulsatility index',
                                      'stenosis',
                                      'occlusion',
                                      'thrombus',
                                      'plaque',
                                      'intima-media thickness',
                                      ' imt '],
                 'llm_system_prompt': (
                                      'You are a radiology data curator specializing in vascular ultrasound. Extract structured information from vascular ultrasound case report text.\n'
                                      'Return ONLY valid JSON with these exact fields:\n'
                                      '{\n'
                                      '  "finding": "primary vascular finding with Doppler parameters (e.g. \'non-compressible left common femoral vein with echogenic thrombus and absent flow on color Doppler\')",\n'
                                      '  "diagnosis": "final diagnosis (e.g. \'deep vein thrombosis\', \'carotid stenosis\')",\n'
                                      '  "laterality": "right | left | bilateral | N/A"\n'
                                      '}\n\n'
                                      '*** STRICT SCOPE RULE — THIS SPECIFIC FIGURE ONLY ***\n'
                                      'You are extracting information for ONE specific figure (identified by Figure legend).\n'
                                      'ONLY use findings explicitly described in the "Figure legend" field.\n'
                                      'Use "Results text", "Case presentation", and "Abstract" ONLY to identify the final diagnosis — never to add findings from other figures.\n'
                                      'DO NOT include findings from: other figures in the same paper, other imaging modalities (CT, MRI, X-ray, catheter angiography, venography), different time points.\n'
                                      'DO NOT mix Doppler findings from one vessel with findings from a different vessel in another figure.\n'
                                      'If the figure legend does not describe a vascular ultrasound finding (e.g., it shows a CT or clinical photo), write "unclear" for finding.\n\n'
                                      'CRITICAL - Vascular ultrasound terminology (include in finding field):\n'
                                      '- Venous: compressibility (non-compressible = DVT), flow (absent/reversed), thrombus echogenicity\n'
                                      '- Arterial: peak systolic velocity (PSV), stenosis %, waveform pattern\n'
                                      '- Waveforms: triphasic (normal artery), monophasic (stenosis/occlusion)\n\n'
                                      'CRITICAL - Diagnosis normalization:\n'
                                      '- "Deep vein thrombosis" NOT "DVT"\n'
                                      '- "Carotid stenosis" (include severity if stated)\n'
                                      '- "Peripheral arterial disease" NOT "PAD"\n'
                                      '- "Abdominal aortic aneurysm" NOT "AAA"\n\n'
                                      'Laterality: right | left | bilateral | N/A\n\n'
                                      "If uncertain, use 'unclear' or 'N/A'. Never return null."
                                      ),
                 'name': 'Vascular Ultrasound',
                 'search_keywords': ['carotid ultrasound',
                                     'carotid doppler',
                                     'vascular ultrasound',
                                     'doppler ultrasound',
                                     'venous ultrasound',
                                     'arterial ultrasound',
                                     'deep vein thrombosis ultrasound',
                                     'DVT ultrasound',
                                     'carotid duplex',
                                     'peripheral vascular ultrasound']},

    # ── MSK_XRAY: plain X-ray and CT for musculoskeletal ─────────────────────
    'MSK_XRAY': {
        'name': 'MSK X-ray / CT',
        'anatomy': 'musculoskeletal',
        'imaging_modality': 'X-ray/CT',
        'diagnosis_terms': [
            'fracture', 'dislocation', 'arthropathy', 'arthritis',
            'calcific tendinosis', 'calcium pyrophosphate', 'CPPD',
            'spondylolysis', 'cervical fracture', 'hip fracture',
            'ankle fracture', 'foot fracture', 'soft tissue sarcoma',
            'enchondroma', 'non-ossifying fibroma', 'fibrous dysplasia',
            'lipoma soft tissue', 'myxoma', 'benign bone tumor',
        ],
        'modality_terms': [
            'radiograph', 'X-ray', 'plain film', 'plain radiograph',
            'CT bone', 'skeletal radiograph',
        ],
        'search_keywords': [
            'musculoskeletal radiograph', 'skeletal radiograph',
            'bone radiograph', 'orthopedic radiograph',
            'fracture radiograph', 'plain radiograph fracture',
            'joint X-ray', 'skeletal X-ray',
            'CT fracture', 'CT musculoskeletal',
            'cervical spine fracture', 'lumbar spine radiograph',
            'hip fracture radiograph', 'knee radiograph',
            'ankle radiograph', 'wrist radiograph',
            'shoulder radiograph', 'foot radiograph',
        ],
        'include_keywords': [
            'plain radiograph', 'plain x-ray', 'plain film',
            'anteroposterior view', 'ap view', 'lateral view',
            'weight-bearing radiograph', 'standing radiograph',
            'ct scan bone', 'ct bone', 'bone window',
            'skeletal survey', 'bone survey',
            'radiograph shows', 'x-ray shows', 'x-ray demonstrates',
        ],
        'exclude_keywords': [
            'chest x-ray', 'chest radiograph', 'cxr', ' pa view',
            'ct chest', 'ct abdomen', 'ct brain', 'ct head',
            'mri', 'magnetic resonance', 'ultrasound', 'sonograph',
            'pet scan', 'bone scan', 'scintigraph',
            'histopath', 'h&e', 'microscop',
            'intraoperative', 'arthroscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            ' acl ': 'ACL injury',
            'anterior cruciate': 'ACL injury',
            'rotator cuff': 'Rotator cuff tear',
            'meniscal tear': 'Meniscal tear',
            'cppd': 'Calcium pyrophosphate disease',
            ' hadd ': 'Calcific tendinosis',
            'calcific tendinitis': 'Calcific tendinosis',
            'spondylolysis': 'Lumbar spondylolysis',
            'scfe': 'Slipped capital femoral epiphysis',
            'perthes': 'Perthes disease',
            'avascular necrosis': 'Avascular necrosis',
            ' avn ': 'Avascular necrosis',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in musculoskeletal imaging. '
            'Extract structured information from musculoskeletal X-ray and CT case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary MSK imaging finding (e.g. \'comminuted fracture of the '
            'femoral neck\', \'joint space narrowing with subchondral sclerosis\', '
            '\'soft tissue calcification at the rotator cuff insertion\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Hip fracture\', \'Osteoarthritis\', '
            '\'Calcific tendinosis\', \'ACL injury\', \'Meniscal tear\')",\n'
            '  "laterality": "right | left | bilateral | N/A"\n'
            '}\n\n'
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            'Laterality: right/left for unilateral joint/bone | bilateral | N/A for axial skeleton.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── MRI_MSK: MRI for musculoskeletal soft tissue ──────────────────────────
    'MRI_MSK': {
        'name': 'MSK MRI',
        'anatomy': 'musculoskeletal',
        'imaging_modality': 'MRI',
        'diagnosis_terms': [
            'ACL injury', 'anterior cruciate ligament tear', 'meniscal tear',
            'rotator cuff tear', 'labral tear', 'Achilles tendon',
            'plantar fasciitis', 'avascular necrosis', 'subchondral insufficiency',
            'extensor mechanism', 'biceps tendon', 'gluteal tendon', 'hamstring tendon',
            'peroneal tendon', 'ankle ligament', 'cartilage osteoarthritis',
        ],
        'modality_terms': [
            'MRI', 'magnetic resonance imaging', 'knee MRI', 'shoulder MRI',
            'hip MRI', 'ankle MRI', 'musculoskeletal MRI',
        ],
        'search_keywords': [
            'knee MRI', 'shoulder MRI', 'hip MRI', 'ankle MRI',
            'wrist MRI', 'musculoskeletal MRI', 'MSK MRI',
            'MRI knee ligament', 'MRI rotator cuff', 'MRI meniscus',
            'MRI tendon', 'MRI labrum', 'MRI soft tissue',
            'magnetic resonance knee', 'magnetic resonance shoulder',
        ],
        'include_keywords': [
            'mri knee', 'knee mri', 'mr knee', 'magnetic resonance knee',
            'mri shoulder', 'shoulder mri', 'mr shoulder',
            'mri hip', 'hip mri', 'mr hip',
            'mri ankle', 'ankle mri', 'mr ankle',
            'mri wrist', 'wrist mri',
            'mri tendon', 'mri ligament', 'mri labrum',
            'mri soft tissue', 'musculoskeletal mri', 'msk mri',
            't2-weighted', 'proton density', 'fat-suppressed mri',
            'stir sequence msk',
        ],
        'exclude_keywords': [
            'mri brain', 'brain mri', 'mri head', 'head mri',
            'mri spine', 'spine mri', 'mri cervical', 'mri lumbar',
            'mri abdomen', 'mri pelvis', 'mri chest', 'mri cardiac',
            'ct scan', ' ct ', 'ultrasound', 'sonograph',
            'x-ray', 'radiograph', 'plain film',
            'pet scan', 'bone scan',
            'histopath', 'h&e', 'microscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            ' acl ': 'ACL injury',
            'anterior cruciate': 'ACL injury',
            ' pcl ': 'PCL injury',
            'posterior cruciate': 'PCL injury',
            'rotator cuff': 'Rotator cuff tear',
            'meniscal tear': 'Meniscal tear',
            'labral tear': 'Labral tear',
            'avascular necrosis': 'Avascular necrosis',
            ' avn ': 'Avascular necrosis',
            'hamstring': 'Hamstring tendon injury',
            'achilles': 'Achilles tendon pathology',
            'plantar fasci': 'Plantar fasciitis',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in musculoskeletal MRI. '
            'Extract structured information from MSK MRI case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary MRI finding (e.g. \'full-thickness ACL tear with bone bruise\', '
            '\'complete supraspinatus tendon tear with retraction\', '
            '\'horizontal medial meniscal tear\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'ACL injury\', \'Rotator cuff tear\', '
            '\'Meniscal tear\', \'Labral tear\', \'Avascular necrosis\')",\n'
            '  "laterality": "right | left | bilateral | N/A"\n'
            '}\n\n'
            'MRI-specific: note signal characteristics (T1, T2, STIR), tear morphology, '
            'degree of injury (partial/complete), associated findings (bone marrow edema, effusion).\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── NM_NUCLEAR: Nuclear medicine PET/SPECT/HIDA ───────────────────────────
    'NM_NUCLEAR': {
        'name': 'Nuclear Medicine',
        'anatomy': 'whole body',
        'imaging_modality': 'Nuclear Medicine',
        'diagnosis_terms': [
            'cardiac sarcoidosis', 'cardiac amyloidosis', 'parathyroid adenoma',
            'cholecystitis', 'biliary atresia', 'thyroid nodule', 'NET metastases',
            'PSMA', 'DOTATATE', 'fever of unknown origin', 'lymphoma',
            'head and neck cancer', 'colon polyp',
            'melanoma', 'sentinel lymph node melanoma', 'DMSA scintigraphy',
            'reactive marrow', 'lung cancer staging', 'FDG PET staging',
        ],
        'modality_terms': [
            'FDG PET', 'PET CT', 'PET-CT', 'HIDA', 'scintigraphy',
            'SPECT', 'nuclear medicine', 'DOTATATE', 'PSMA PET',
        ],
        'search_keywords': [
            'FDG PET CT case report', 'PET scan case report',
            'HIDA scan case report', 'hepatobiliary scintigraphy',
            'thyroid scintigraphy case', 'parathyroid scintigraphy',
            'DOTATATE PET case', 'PSMA PET case report',
            'bone scintigraphy case', 'nuclear medicine case report',
            'SPECT CT case report', 'PYP scintigraphy cardiac amyloid',
            'FDG PET sarcoidosis', 'FDG PET lymphoma',
        ],
        'include_keywords': [
            'fdg pet', 'pet-ct', 'pet ct', 'pet scan',
            'hida scan', 'hepatobiliary scintigraphy', 'cholescintigraphy',
            'thyroid scan', 'thyroid scintigraphy', 'thyroid uptake',
            'parathyroid scan', 'parathyroid scintigraphy', 'sestamibi',
            'dotatate', 'dotatoc', 'gallium', 'ga-68',
            'psma pet', 'psma scan',
            'pyp scan', 'pyp scintigraphy', 'technetium pyrophosphate',
            'bone scan', 'bone scintigraphy',
            'spect', 'spect/ct', 'spect ct',
            'nuclear medicine', 'scintigraphy',
            'dmsa scan', 'mag3 scan', 'renography',
        ],
        'exclude_keywords': [
            'ct chest', 'ct abdomen', 'ct brain', 'mri', 'magnetic resonance',
            'ultrasound', 'sonograph', 'echocardiograph',
            'chest x-ray', 'chest radiograph', 'plain film',
            'histopath', 'h&e', 'microscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'fdg': 'FDG PET',
            'sarcoidosis': 'Cardiac sarcoidosis',
            'amyloid': 'Cardiac amyloidosis',
            'thyroid nodule': 'Thyroid nodule',
            'graves': "Graves disease",
            'cholecystitis': 'Acute cholecystitis',
            'biliary atresia': 'Biliary atresia',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in nuclear medicine. '
            'Extract structured information from nuclear medicine / PET / SPECT case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary nuclear medicine finding (e.g. \'focal FDG-avid lesion in right '
            'lower lobe\', \'non-visualization of the gallbladder on HIDA\', '
            '\'increased uptake in cervical lymph nodes on DOTATATE\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Pulmonary NET\', '
            '\'Acute cholecystitis\', \'Cardiac sarcoidosis\', \'Parathyroid adenoma\')",\n'
            '  "laterality": "right | left | bilateral | central | N/A"\n'
            '}\n\n'
            'Specify the radionuclide/tracer in the finding when available.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── MRI_ABDOMEN: GI body MRI — liver, pancreas, bowel, rectum ────────────
    'MRI_ABDOMEN': {
        'name': 'MRI Abdomen (GI)',
        'anatomy': 'abdomen',
        'imaging_modality': 'MRI',
        # Anatomy/procedure-first retrieval. Diagnosis is extracted after
        # figure retrieval and does not restrict the PMC search universe.
        'search_keywords': [
            'MRI abdomen', 'abdominal MRI', 'MR abdomen',
            'magnetic resonance abdomen', 'magnetic resonance imaging abdomen',
            'liver MRI', 'hepatic MRI', 'MRI liver',
            'pancreatic MRI', 'MRI pancreas',
            'MRCP', 'MR cholangiopancreatography',
            'MR enterography', 'magnetic resonance enterography',
            'bowel MRI', 'small bowel MRI',
            'rectal MRI', 'MRI rectum',
        ],
        'include_keywords': [
            'mri abdomen', 'abdominal mri', 'mr abdomen', 'mri of the abdomen',
            'mrcp', 'mr cholangiopancreatography',
            'liver mri', 'hepatic mri', 'mri liver', 'mri of the liver',
            'rectal mri', 'mri rectum', 'mri of the rectum',
            'mri pancreas', 'pancreatic mri',
            'body mri', 'magnetic resonance imaging abdomen',
            'contrast-enhanced mri abdomen', 'gadolinium abdomen',
            'hepatobiliary phase', 'primovist', 'eovist',
            't2-weighted abdomen', 'diffusion-weighted liver',
            'dwi liver', 'dwi abdomen',
            # IBD / bowel MRI terms (align with search_keywords)
            'mr enterography', 'mri enterography', 'magnetic resonance enterography',
            'bowel mri', 'small bowel mri', 'crohn mri', 'ibd mri',
            # MR urogram / urography (GU — MR urogram gap fill)
            'mr urogram', 'mr urography', 'magnetic resonance urogram',
            'magnetic resonance urography', 'mru',
        ],
        'exclude_keywords': [
            'ct abdomen', 'ct scan abdomen', 'computed tomography abdomen',
            'mri brain', 'brain mri', 'mri spine', 'spine mri',
            'mri knee', 'mri shoulder', 'mri hip', 'mri pelvis',
            'mri prostate', 'mri uterus', 'mri cervix', 'mri bladder',
            'chest mri', 'mri chest', 'cardiac mri',
            'ultrasound', 'sonograph',
            'pet scan', 'scintigraph',
            'chest x-ray', 'radiograph',
            'histopath', 'h&e', 'microscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'hcc': 'Hepatocellular carcinoma',
            'hepatocellular carcinoma': 'Hepatocellular carcinoma',
            'fnl': 'Focal nodular hyperplasia',
            'focal nodular hyperplasia': 'Focal nodular hyperplasia',
            'hepatic adenoma': 'Hepatic adenoma',
            'ipmn': 'IPMN',
            'intraductal papillary': 'IPMN',
            'cholangiocarcinoma': 'Cholangiocarcinoma',
            'psc': 'Primary sclerosing cholangitis',
            'primary sclerosing cholangitis': 'Primary sclerosing cholangitis',
            'choledocholithiasis': 'Choledocholithiasis',
            'rectal cancer': 'Rectal carcinoma',
            'rectal carcinoma': 'Rectal carcinoma',
            'crohn': 'Crohn disease',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in abdominal MRI. '
            'Extract structured information from abdominal MRI case reports, '
            'including liver, pancreas, biliary tract, bowel, and retroperitoneum.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary MRI finding (e.g. \'T1 hypointense T2 hyperintense hepatic '
            'lesion with arterial enhancement and washout\', \'dilated bile ducts with filling '
            'defect on MRCP\', \'T2 hyperintense rectal wall thickening with mesorectal '
            'lymphadenopathy\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Hepatocellular carcinoma\', '
            '\'Choledocholithiasis\', \'Rectal carcinoma\', \'IPMN\', \'Focal nodular hyperplasia\')",\n'
            '  "laterality": "right | left | bilateral | central | N/A"\n'
            '}\n\n'
            'Note MRI-specific features: signal intensity on T1/T2, enhancement pattern '
            '(arterial/portal/delayed/hepatobiliary phase), diffusion restriction.\n'
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── MRI_PELVIS: GU pelvic MRI — prostate, uterus, cervix, bladder ────────
    'MRI_PELVIS': {
        'name': 'MRI Pelvis (GU)',
        'anatomy': 'pelvis',
        'imaging_modality': 'MRI',
        # Anatomy/procedure-first retrieval. Diagnosis is extracted after
        # figure retrieval and does not restrict the PMC search universe.
        'search_keywords': [
            'MRI pelvis', 'pelvic MRI', 'MR pelvis',
            'magnetic resonance pelvis', 'magnetic resonance imaging pelvis',
            'MRI prostate', 'prostate MRI', 'multiparametric prostate MRI',
            'mpMRI prostate',
            'MRI bladder', 'bladder MRI',
            'MRI uterus', 'uterine MRI',
            'MRI cervix', 'cervical MRI',
            'MRI ovary', 'ovarian MRI',
            'adnexal MRI', 'female pelvic MRI',
        ],
        'include_keywords': [
            'mri pelvis', 'pelvic mri', 'mr pelvis', 'mri of the pelvis',
            'mri prostate', 'prostate mri', 'mpmri', 'multiparametric mri',
            'pi-rads', 'pirads',
            'mri uterus', 'uterine mri', 'mri of the uterus',
            'mri cervix', 'cervical mri', 'mri of the cervix',
            'mri bladder', 'bladder mri',
            'mri ovary', 'ovarian mri',
            'magnetic resonance pelvis', 'magnetic resonance imaging pelvis',
            'gadolinium pelvis', 't2-weighted pelvis',
            'diffusion-weighted pelvis', 'dwi pelvis',
        ],
        'exclude_keywords': [
            'ct pelvis', 'ct scan pelvis', 'computed tomography pelvis',
            'mri brain', 'brain mri', 'mri spine', 'spine mri',
            'mri knee', 'mri shoulder', 'mri hip',
            'mri abdomen', 'abdominal mri', 'mri liver',
            'chest mri', 'mri chest',
            'ultrasound', 'sonograph',
            'pet scan', 'scintigraph',
            'chest x-ray', 'radiograph', 'plain film',
            'histopath', 'h&e', 'microscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'prostate cancer': 'Prostate carcinoma',
            'prostate carcinoma': 'Prostate carcinoma',
            'pi-rads': 'Prostate carcinoma',
            'leiomyoma': 'Uterine leiomyoma',
            'fibroid': 'Uterine leiomyoma',
            'leiomyosarcoma': 'Uterine leiomyosarcoma',
            'endometrial cancer': 'Endometrial carcinoma',
            'endometrial carcinoma': 'Endometrial carcinoma',
            'cervical cancer': 'Cervical carcinoma',
            'cervical carcinoma': 'Cervical carcinoma',
            'endometrioma': 'Ovarian endometrioma',
            'ovarian cancer': 'Ovarian carcinoma',
            'bladder cancer': 'Bladder carcinoma',
            'urothelial carcinoma': 'Bladder carcinoma',
            'placenta accreta': 'Placenta accreta spectrum',
            'mullerian': 'Mullerian anomaly',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in pelvic MRI. '
            'Extract structured information from pelvic MRI case reports, '
            'including prostate, uterus, cervix, ovaries, and bladder.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary MRI finding (e.g. \'T2 hypointense lesion in the peripheral '
            'zone of the prostate with restricted diffusion PI-RADS 5\', \'T2 hyperintense '
            'submucosal uterine mass with heterogeneous signal\', \'irregular T2 hypointense '
            'cervical mass with parametrial invasion\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Prostate carcinoma\', '
            '\'Uterine leiomyoma\', \'Cervical carcinoma\', \'Endometrial carcinoma\', '
            '\'Ovarian endometrioma\')",\n'
            '  "laterality": "right | left | bilateral | midline | N/A"\n'
            '}\n\n'
            'Note MRI-specific features: T2 signal, enhancement pattern, DWI/ADC values, '
            'PI-RADS score for prostate, FIGO staging elements for gynecologic malignancies.\n'
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── GI_FLUOROSCOPY: ABR GI radiography/fluoroscopy domain ───────────────
    'GI_FLUOROSCOPY': {
        'name': 'GI Radiography / Fluoroscopy',
        'anatomy': 'gastrointestinal tract',
        'imaging_modality': 'Fluoroscopy',
        # Procedure-first search: deliberately not restricted to a hand-picked
        # diagnosis list. Disease is extracted after retrieval.
        'search_keywords': [
            'esophagram', 'barium swallow',
            'upper GI series', 'upper gastrointestinal series',
            'small bowel follow-through', 'small bowel follow through',
            'enteroclysis', 'contrast enema', 'barium enema',
            'fluoroscopic swallowing study', 'videofluoroscopic swallow study',
        ],
        'include_keywords': [
            'esophagram', 'oesophagram', 'barium swallow',
            'upper gi series', 'upper gastrointestinal series', 'ugi series',
            'small bowel follow-through', 'small bowel follow through',
            'small bowel series', 'enteroclysis',
            'contrast enema', 'barium enema',
            'fluoroscopic swallowing study', 'videofluoroscopic swallow',
            'modified barium swallow',
            'fluoroscopic image', 'fluoroscopic spot image',
        ],
        'exclude_keywords': [
            'endoscopy', 'endoscopic', 'colonoscopy', 'gastroscopy',
            'capsule endoscopy', 'intraoperative', 'surgical photograph',
            'ct scan', 'computed tomography', 'mri', 'magnetic resonance',
            'ultrasound', 'sonograph', 'pet/ct', 'pet scan', 'scintigraph',
            'histopath', 'h&e', 'hematoxylin', 'microscop',
            'flowchart', 'flow chart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'achalasia': 'Achalasia',
            'esophageal perforation': 'Esophageal perforation',
            'esophageal stricture': 'Esophageal stricture',
            'malrotation': 'Intestinal malrotation',
            'volvulus': 'Volvulus',
            'hirschsprung': 'Hirschsprung disease',
            'aspiration': 'Aspiration',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in gastrointestinal '
            'radiography and fluoroscopy. Extract structured information from '
            'esophagram, swallowing, upper GI, small-bowel, enteroclysis, and '
            'contrast-enema case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary fluoroscopic finding, including contrast passage, '
            'contour, obstruction, leak, reflux, aspiration, or motility abnormality",\n'
            '  "diagnosis": "final clinical diagnosis",\n'
            '  "laterality": "right | left | bilateral | central | midline | N/A"\n'
            '}\n\n'
            'Describe only findings visible on the radiographic or fluoroscopic figure. '
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── GU_FLUOROSCOPY: ABR GU radiography/fluoroscopy domain ───────────────
    'GU_FLUOROSCOPY': {
        'name': 'GU Radiography / Fluoroscopy',
        'anatomy': 'genitourinary tract/pelvis',
        'imaging_modality': 'Fluoroscopy',
        # Procedure-first search: deliberately not restricted to a hand-picked
        # diagnosis list. Disease is extracted after retrieval.
        'search_keywords': [
            'voiding cystourethrogram', 'voiding cystourethrography', 'VCUG',
            'retrograde urethrogram', 'retrograde urethrography',
            'cystogram', 'fluoroscopic cystography',
            'hysterosalpingography', 'hysterosalpingogram', 'HSG',
            'genitourinary fluoroscopy',
        ],
        'include_keywords': [
            'voiding cystourethrogram', 'voiding cystourethrography', 'vcug',
            'micturating cystourethrogram', 'micturating cystourethrography', 'mcug',
            'retrograde urethrogram', 'retrograde urethrography',
            'ascending urethrogram',
            'cystogram', 'cystography',
            'hysterosalpingography', 'hysterosalpingogram', 'hsg',
            'fluoroscopic image', 'fluoroscopic spot image',
        ],
        'exclude_keywords': [
            'cystoscopy', 'hysteroscopy', 'laparoscopy', 'endoscopy',
            'intraoperative', 'surgical photograph',
            'ct cystography', 'ct scan', 'computed tomography',
            'mri', 'magnetic resonance', 'ultrasound', 'sonograph',
            'pet/ct', 'pet scan', 'scintigraph',
            'histopath', 'h&e', 'hematoxylin', 'microscop',
            'flowchart', 'flow chart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'vesicoureteral reflux': 'Vesicoureteral reflux',
            'posterior urethral valve': 'Posterior urethral valves',
            'urethral stricture': 'Urethral stricture',
            'bladder rupture': 'Bladder rupture',
            'uterine anomaly': 'Mullerian anomaly',
            'mullerian anomaly': 'Mullerian anomaly',
            'tubal occlusion': 'Fallopian tube occlusion',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in genitourinary '
            'radiography and fluoroscopy. Extract structured information from '
            'VCUG, cystography, urethrography, and hysterosalpingography case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary fluoroscopic finding, including reflux, urethral '
            'caliber, bladder contour, contrast leak, uterine cavity, or tubal patency",\n'
            '  "diagnosis": "final clinical diagnosis",\n'
            '  "laterality": "right | left | bilateral | central | midline | N/A"\n'
            '}\n\n'
            'Describe only findings visible on the radiographic or fluoroscopic figure. '
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── CT_CHEST_VASC: Thoracic vascular CT ──────────────────────────────────
    'CT_CHEST_VASC': {
        'name': 'CT Chest Vascular',
        'anatomy': 'chest',
        'imaging_modality': 'CT',
        'diagnosis_terms': [
            'aortic dissection', 'aortic aneurysm', 'penetrating aortic ulcer',
            'aortic laceration', 'thoracic lymphoma', 'Hodgkin lymphoma',
            'invasive aspergillosis', 'aspergillosis', 'lung torsion',
            'heterotaxy', 'right aortic arch', 'aberrant subclavian',
            'malpositioned ETT', 'fractured bronchus',
            'desquamative interstitial pneumonia', 'DIP lung',
            'lung cancer staging', 'pancreatic laceration',
        ],
        'modality_terms': [
            'CT chest', 'chest CT', 'CT angiography', 'CTA chest',
            'computed tomography chest', 'thoracic CT',
        ],
        'search_keywords': [
            'aortic dissection CT case report', 'aortic aneurysm CT case',
            'thoracic aorta CT case', 'CTA chest case report',
            'CT angiography aorta', 'aortic injury CT',
            'thoracic lymphoma CT', 'invasive aspergillosis CT',
            'malpositioned central line radiograph',
            'congenital aortic arch anomaly CT',
        ],
        'include_keywords': [
            'ct chest', 'chest ct', 'ct of the chest', 'ct thorax',
            'ct angiography chest', 'cta chest', 'cta aorta',
            'ct aorta', 'aortic ct', 'thoracic ct',
            'contrast-enhanced ct chest', 'cect chest',
            'chest ct scan', 'ct of the thorax',
        ],
        'exclude_keywords': [
            'ct abdomen', 'ct brain', 'ct head', 'ct pelvis',
            'chest x-ray', 'chest xray', 'chest radiograph', ' cxr ',
            'mri', 'magnetic resonance',
            'ultrasound', 'sonograph',
            'pet scan', 'fdg',
            'histopath', 'h&e', 'microscop',
            'intraoperative', 'thoracoscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'aortic dissection': 'Aortic dissection',
            'stanford type a': 'Aortic dissection type A',
            'stanford type b': 'Aortic dissection type B',
            'aortic aneurysm': 'Aortic aneurysm',
            'penetrating aortic ulcer': 'Penetrating aortic ulcer',
            'aspergillosis': 'Invasive aspergillosis',
            'lymphoma chest': 'Thoracic lymphoma',
            'hodgkin': 'Hodgkin lymphoma',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in thoracic CT. '
            'Extract structured information from thoracic CT case reports, '
            'focusing on vascular, mediastinal, and complex chest pathology.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary CT chest finding (e.g. \'intimal flap extending from the '
            'aortic root to the descending aorta\', \'fusiform aortic aneurysm measuring 5.8 cm\', '
            '\'cavitary lung lesion with halo sign\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Aortic dissection type A\', '
            '\'Thoracic aortic aneurysm\', \'Invasive aspergillosis\', \'Thoracic lymphoma\')",\n'
            '  "laterality": "right | left | bilateral | central | mediastinal | N/A"\n'
            '}\n\n'
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── MRI_NEURO_SPINE: Neuro MRI / CT for spine and skull ──────────────────
    'MRI_NEURO_SPINE': {
        'name': 'Neuro MRI / CT (Spine & Skull)',
        'anatomy': 'neuro spine',
        'imaging_modality': 'MRI/CT',
        'diagnosis_terms': [
            'skull fracture', 'spine fracture', 'cervical fracture',
            'atlanto-occipital dislocation', 'epidural hematoma', 'epidural abscess',
            'spinal subdural hematoma', 'bone metastasis spine',
            'epidural tumor', 'Guillain-Barre', 'demyelination spinal cord',
            'optic neuritis', 'fungal sinusitis',
        ],
        'modality_terms': [
            'spine MRI', 'brain MRI', 'MRI spine', 'MRI brain',
            'CT skull', 'spinal CT', 'CT spine', 'magnetic resonance spine',
        ],
        'search_keywords': [
            'spine fracture CT MRI case', 'skull fracture CT case report',
            'spinal cord demyelination MRI', 'epidural hematoma MRI CT',
            'epidural abscess MRI', 'spinal metastasis MRI',
            'Guillain-Barre MRI', 'optic neuritis MRI',
            'fungal sinusitis CT MRI', 'atlanto-occipital dislocation CT',
        ],
        'include_keywords': [
            'mri spine', 'spine mri', 'spinal mri', 'mr spine',
            'ct spine', 'spine ct', 'spinal ct',
            'mri cervical', 'cervical mri', 'mri lumbar', 'lumbar mri',
            'mri thoracic spine', 'thoracic spine mri',
            'ct skull', 'skull ct', 'ct head bone', 'bone window',
            'mri brain', 'brain mri',
            'ct sinuses', 'sinus ct', 'facial ct',
            'spinal cord mri', 'mri cord',
        ],
        'exclude_keywords': [
            'ct chest', 'ct abdomen', 'ct pelvis',
            'chest x-ray', 'chest radiograph',
            'ultrasound', 'sonograph',
            'pet scan', 'bone scan', 'fdg',
            'histopath', 'h&e', 'microscop',
            'flowchart', 'diagram', 'schematic', ' table ',
            'knee mri', 'shoulder mri', 'hip mri', 'ankle mri',
            'musculoskeletal mri',
        ],
        'diagnosis_normalization': {
            'skull fracture': 'Acute skull fracture',
            'spine fracture': 'Acute spine fracture',
            'cervical fracture': 'Cervical fracture',
            'epidural hematoma': 'Epidural hematoma',
            'epidural abscess': 'Epidural abscess',
            'guillan-barre': 'Guillain-Barre syndrome',
            'guillain barre': 'Guillain-Barre syndrome',
            'aidp': 'Guillain-Barre syndrome',
            'demyelination': 'Acute demyelination',
            'optic neuritis': 'Acute optic neuritis',
            'fungal sinusitis': 'Invasive fungal sinusitis',
            'bone metastasis spine': 'Bone metastasis in the spine',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in neuroimaging and spine MRI/CT. '
            'Extract structured information from neuro MRI and spine CT case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary neuro/spine finding (e.g. \'burst fracture of L1 with '
            'retropulsion\', \'T2 hyperintense lesion in the cervical spinal cord\', '
            '\'epidural fluid collection with cord compression\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Acute spine fracture\', '
            '\'Acute demyelination\', \'Epidural abscess\', \'Guillain-Barre syndrome\')",\n'
            '  "laterality": "right | left | bilateral | central | midline | N/A"\n'
            '}\n\n'
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

    # ── US_GYN_TRANS: Gynecologic, testicular, transplant US ─────────────────
    'US_GYN_TRANS': {
        'name': 'US Gynecologic / Testicular / Transplant',
        'anatomy': 'pelvis/testis/transplant',
        'imaging_modality': 'Ultrasound',
        'diagnosis_terms': [
            'ovarian cyst', 'hemorrhagic cyst', 'ovarian malignancy',
            'sex cord stromal tumor', 'epididymo-orchitis', 'testicular rupture',
            'testicular hematoma', 'subchorionic hemorrhage',
            'transplant hepatic artery stenosis', 'transplant renal vein thrombosis',
            'pancreatic transplant', 'soft tissue lipoma',
            'congenital uterine anomaly', 'uterine anomaly', 'Mullerian anomaly',
            'germinal matrix hemorrhage', 'multicystic dysplastic kidney',
            'Fournier gangrene', 'perianal fistula',
            'congenital duodenal obstruction', 'hip dysplasia infant',
        ],
        'modality_terms': [
            'ultrasound', 'sonography', 'Doppler', 'pelvic ultrasound',
            'scrotal ultrasound', 'transvaginal ultrasound',
        ],
        'search_keywords': [
            'ovarian cyst ultrasound case report', 'gynecologic ultrasound case',
            'testicular ultrasound case report', 'scrotal ultrasound case',
            'transplant Doppler ultrasound case', 'renal transplant ultrasound',
            'hepatic transplant ultrasound', 'epididymo-orchitis ultrasound',
            'subchorionic hemorrhage ultrasound', 'ovarian torsion ultrasound',
        ],
        'include_keywords': [
            'pelvic ultrasound', 'transvaginal ultrasound', 'transabdominal ultrasound',
            'gynecologic ultrasound', 'obstetric ultrasound',
            'scrotal ultrasound', 'testicular ultrasound', 'scrotal sonograph',
            'transplant doppler', 'renal transplant ultrasound',
            'hepatic transplant ultrasound', 'liver transplant doppler',
            'doppler ultrasound transplant',
            'soft tissue ultrasound', 'superficial ultrasound',
        ],
        'exclude_keywords': [
            'ct scan', 'mri', 'magnetic resonance',
            'chest x-ray', 'chest radiograph',
            'pet scan', 'bone scan',
            'abdominal ultrasound liver', 'hepatic ultrasound',
            'carotid doppler', 'vascular doppler',
            'histopath', 'h&e', 'microscop',
            'flowchart', 'diagram', 'schematic', ' table ',
        ],
        'diagnosis_normalization': {
            'epididymo-orchitis': 'Acute epididymo-orchitis',
            'epididymoorchitis': 'Acute epididymo-orchitis',
            'testicular torsion': 'Testicular torsion',
            'testicular rupture': 'Testicular rupture',
            'ovarian cyst': 'Ovarian cyst',
            'hemorrhagic cyst': 'Ovarian hemorrhagic cyst',
            'subchorionic': 'Subchorionic hemorrhage',
            'ovarian malignancy': 'Ovarian malignant neoplasm',
            'sex cord stromal': 'Ovarian sex cord stromal tumor',
            'hepatic artery stenosis': 'Transplant hepatic artery stenosis',
            'renal vein thrombosis': 'Transplant renal vein thrombosis',
            'pancreatic transplant': 'Pancreatic transplant',
        },
        'llm_system_prompt': (
            'You are a radiology data curator specializing in gynecologic, testicular, '
            'and transplant ultrasound. Extract structured information from ultrasound case reports.\n'
            'Return ONLY valid JSON with these exact fields:\n'
            '{\n'
            '  "finding": "primary ultrasound finding (e.g. \'complex adnexal cyst with internal '
            'hemorrhage\', \'heterogeneous testicular mass with increased vascularity\', '
            '\'elevated resistive index in transplant renal artery\')",\n'
            '  "diagnosis": "final clinical diagnosis (e.g. \'Ovarian hemorrhagic cyst\', '
            '\'Acute epididymo-orchitis\', \'Transplant renal artery stenosis\')",\n'
            '  "laterality": "right | left | bilateral | N/A"\n'
            '}\n\n'
            'Extraction priority: figure legend and results text are PRIMARY sources.\n'
            "If uncertain, use 'unclear' or 'N/A'. Never return null."
        ),
    },

}

# Production-ready configurations for the remaining collection routes. Kept in
# a separate additive module so historical modality definitions remain intact.
from openredu.collection_expansion_config import COLLECTION_EXPANSION_MODALITY_CONFIG
MODALITY_CONFIG.update(COLLECTION_EXPANSION_MODALITY_CONFIG)

# All modalities are now in MODALITY_CONFIG. GAP_FILL_MODALITY_CONFIG kept as
# empty dict for backward compatibility with code that imports it.
GAP_FILL_MODALITY_CONFIG: dict = {}
