# Caption dictionaries and normalization maps


Transcribed from `config/keyword_dictionaries_and_normalization_maps.json`, which is the machine-readable source. Exclusion terms take precedence over inclusion terms.

#### BREAST_MRI

**Search keywords.** breast MRI; MRI of the breast; breast magnetic resonance imaging; dynamic contrast-enhanced breast MRI.

**Include keywords.** breast mri; mri of the breast; breast magnetic resonance; dynamic contrast-enhanced breast; dce-mri breast.

**Exclude keywords.** mammogram; mammography; breast ultrasound; breast sonography; breast ct; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### BREAST_ULTRASOUND

**Search keywords.** breast ultrasound; breast ultrasonography; breast sonography; ultrasound of the breast.

**Include keywords.** breast ultrasound; breast ultrasonography; breast sonography; ultrasound of the breast; breast doppler.

**Exclude keywords.** mammogram; mammography; breast mri; magnetic resonance; breast ct; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### CARDIOVASCULAR_MRI

**Search keywords.** cardiac MRI; cardiac magnetic resonance; cardiovascular magnetic resonance; cardiac MR imaging; CMR imaging.

**Include keywords.** cardiac mri; cardiac magnetic resonance; cardiovascular magnetic resonance; cardiac mr imaging; cmr imaging; late gadolinium enhancement.

**Exclude keywords.** cardiac ct; coronary ct; echocardiograph; spect; pet/ct; scintigraph; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### CT_ABDOMEN

**Search keywords.** CT abdomen; abdominal CT; abdominal computed tomography; computed tomography abdomen; CT of the abdomen; CT pelvis; abdominopelvic CT; CT scan abdomen; contrast-enhanced CT abdomen; CT urography; CT colonography.

**Include keywords.** ct abdomen; abdominal ct; ct of the abdomen; ct scan abdomen; ct of abdomen; computed tomography abdomen; computed tomography of the abdomen; abdominopelvic ct; ct abdomen and pelvis; ct abdomen/pelvis; ct pelvis; pelvic ct; ct of the pelvis; contrast-enhanced ct abdomen; contrast enhanced ct abdomen; portal venous phase ct; arterial phase ct; cect abdomen; cect of abdomen; triple-phase ct; triphasic ct; ct of the liver; liver ct; hepatic ct; ct of the pancreas; pancreatic ct; ct kidney; renal ct; ct of the kidney; ct urography; ct kub; ct colonography; virtual colonoscopy; mdct abdomen; non-contrast ct abdomen.

**Exclude keywords.** ct brain; brain ct; ct head; head ct; cranial ct; ct chest; chest ct; ct of the chest; ct thorax; ct pulmonary; hrct; ctpa; ct spine; spine ct; ct of the spine; ct lumbar; lumbar ct; ct cervical spine; ct neck; neck ct; ct of the neck; ct chest abdomen; whole body ct; pan-scan; chest x-ray; chest xray; chest radiograph;  cxr ; abdominal x-ray; plain abdominal; mri abdomen; abdominal mri; magnetic resonance; abdominal ultrasound; hepatic ultrasound; sonograph; pet scan; pet-ct; fdg; histopath; h&e; hematoxylin; microscop; intraoperative; laparoscop; colonoscop; flowchart; flow chart; flow-chart;  diagram; schematic; algorithm; study design; protocol; workflow;  table ; timeline;  bar graph; bar chart;  pie chart.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  fnh  | Focal nodular hyperplasia |
|  gist  | Gastrointestinal stromal tumor |
|  hcc  | Hepatocellular carcinoma |
|  pnet  | Pancreatic neuroendocrine tumor |
|  rcc  | Renal cell carcinoma |
| angiomyolipoma | Renal angiomyolipoma |
| appendicitis | Acute appendicitis |
| cholangiocarcinoma | Cholangiocarcinoma |
| focal nodular hyperplasia | Focal nodular hyperplasia |
| gastrointestinal stromal | Gastrointestinal stromal tumor |
| hemangioma | Hepatic hemangioma |
| hepatocellular carcinoma | Hepatocellular carcinoma |
| hepatoma | Hepatocellular carcinoma |
| ipmn | Intraductal papillary mucinous neoplasm |
| lymphoma | Lymphoma |
| pancreatic ductal adenocarcinoma | Pancreatic adenocarcinoma |
| pancreatic neuroendocrine | Pancreatic neuroendocrine tumor |
| pdac | Pancreatic adenocarcinoma |
| pheochromocytoma | Pheochromocytoma |
| renal cell carcinoma | Renal cell carcinoma |
| transitional cell | Urothelial carcinoma |
| urothelial carcinoma | Urothelial carcinoma |

#### CT_BRAIN

**Search keywords.** CT brain; brain CT; CT head; head CT; brain computed tomography; computed tomography brain; non-contrast CT brain; NCCT brain; NECT brain; CT angiography brain; CTA brain; CT perfusion brain.

**Include keywords.** ct brain; brain ct; ct of the brain; ct of brain; ct head; head ct; ct of the head; computed tomography brain; computed tomography head; brain computed tomography; ct scan brain; ct scan head; non-contrast ct brain; noncontrast ct brain; ncct brain; nect brain; ncct head; nect head; non-enhanced ct brain; unenhanced ct brain; cta brain; cta head; ct angiography brain; ct angiography head; cerebral cta; cranial cta; ct perfusion brain; ct perfusion head; cranial ct; ct cranial; cranial computed tomography; intracranial ct; ct intracranial.

**Exclude keywords.** ct chest; chest ct; ct of the chest; ct thorax; ct pulmonary; hrct; ctpa; ct abdomen; abdominal ct; ct of the abdomen; ct pelvis; pelvic ct; abdominopelvic ct; ct spine; spine ct; ct of the spine; ct lumbar; lumbar ct; ct cervical spine; ct neck; neck ct; ct of the neck; ct soft tissue neck; ct head and neck; whole body ct; pan-scan; mri brain; brain mri; magnetic resonance brain; mri head; head mri; cranial mri; flair; diffusion-weighted;  dwi ;  adc ; susceptibility-weighted;  swi ; chest x-ray; chest xray; chest radiograph;  cxr ; pet scan; pet-ct; fdg; cerebral angiograph; histopath; h&e; hematoxylin; microscop; intraoperative; flowchart; flow chart; flow-chart;  diagram; schematic; algorithm; study design; protocol; workflow;  table ; timeline;  bar graph; bar chart;  pie chart.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  avm  | Arteriovenous malformation |
|  cva  | Acute ischemic stroke |
|  cvst  | Cerebral venous thrombosis |
|  cvt  | Cerebral venous thrombosis |
|  edh  | Epidural hematoma |
|  gbm  | Glioblastoma |
|  ich  | Intracerebral hemorrhage |
|  sah  | Subarachnoid hemorrhage |
|  sdh  | Subdural hematoma |
|  tbi  | Traumatic brain injury |
| arteriovenous malformation | Arteriovenous malformation |
| brain abscess | Brain abscess |
| brain metastases | Brain metastasis |
| cerebral abscess | Brain abscess |
| cerebral infarct | Acute ischemic stroke |
| cerebral venous thrombosis | Cerebral venous thrombosis |
| diffuse axonal injury | Diffuse axonal injury |
| epidural hematoma | Epidural hematoma |
| glioblastoma | Glioblastoma |
| glioblastoma multiforme | Glioblastoma |
| hydrocephalus | Hydrocephalus |
| intracerebral hemorrhage | Intracerebral hemorrhage |
| intraparenchymal hemorrhage | Intracerebral hemorrhage |
| ischemic stroke | Acute ischemic stroke |
| meningioma | Meningioma |
| subarachnoid hemorrhage | Subarachnoid hemorrhage |
| subdural hematoma | Subdural hematoma |
| traumatic brain injury | Traumatic brain injury |

#### CT_CHEST

**Search keywords.** CT chest; chest CT; chest computed tomography; computed tomography chest; HRCT chest; high-resolution CT; CT pulmonary; CT thorax; thoracic CT; CTPA; CT pulmonary angiography; low-dose CT chest.

**Include keywords.** ct chest; chest ct; ct thorax; thoracic ct; computed tomography chest; computed tomography of the chest; chest computed tomography; ct of the chest; ct of chest; ct scan of the chest; ct scan chest; chest ct scan; ct pulmonary; hrct chest; hrct lung; hrct of the lung; high-resolution ct; high resolution ct; ctpa; ct pulmonary angiograph; low-dose ct; ldct chest; thorax ct; ct thoracic; contrast-enhanced ct chest; contrast enhanced ct chest; non-contrast ct chest; noncontrast ct chest; ct scan of thorax; ct of thorax.

**Exclude keywords.** ct brain; brain ct; ct head; head ct; ct of the brain; cranial ct; ncct brain; ct abdomen; abdominal ct; ct of the abdomen; ct pelvis; pelvic ct; abdominopelvic ct; ct spine; spine ct; ct of the spine; ct lumbar; lumbar ct; ct cervical spine; ct thoracic spine; ct neck; neck ct; ct of the neck; ct chest abdomen; ct chest and abdomen; ct chest/abdomen; whole body ct; pan-scan; chest x-ray; chest xray; chest radiograph; chest x ray;  cxr ; plain chest; chest film; pa view; ap view; posteroanterior; anteroposterior; mri chest; chest mri; magnetic resonance; pet scan; pet-ct; fdg; ultrasound; echocardiograph; sonograph; bronchoscop; endoscop; mammogr; mammogram; histopath; h&e; hematoxylin; microscop; intraoperative; flowchart; flow chart; flow-chart;  diagram; schematic; algorithm; study design; protocol; workflow;  table ; timeline;  bar graph; bar chart;  pie chart.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  ipf  | Idiopathic pulmonary fibrosis |
|  pcp  | Pneumocystis pneumonia |
|  pe  | Pulmonary embolism |
|  tb  | Tuberculosis |
|  uip  | UIP pattern |
| adenocarcinoma | Lung adenocarcinoma |
| aspergill | Pulmonary aspergillosis |
| carcinoid | Pulmonary carcinoid tumor |
| covid | COVID-19 pneumonia |
| hamartoma | Pulmonary hamartoma |
| idiopathic pulmonary fibrosis | Idiopathic pulmonary fibrosis |
| mesothelioma | Mesothelioma |
| non-small cell | Non-small cell lung cancer |
| pneumocystis | Pneumocystis pneumonia |
| pulmonary embolism | Pulmonary embolism |
| sarcoid | Sarcoidosis |
| sars-cov | COVID-19 pneumonia |
| small cell | Small cell lung cancer |
| squamous cell carcinoma | Squamous cell carcinoma of lung |
| thymoma | Thymoma |
| tuberculosis | Tuberculosis |

#### CT_CHEST_VASC

**Search keywords.** aortic dissection CT case report; aortic aneurysm CT case; thoracic aorta CT case; CTA chest case report; CT angiography aorta; aortic injury CT; thoracic lymphoma CT; invasive aspergillosis CT; malpositioned central line radiograph; congenital aortic arch anomaly CT.

**Diagnosis terms.** aortic dissection; aortic aneurysm; penetrating aortic ulcer; aortic laceration; thoracic lymphoma; Hodgkin lymphoma; invasive aspergillosis; aspergillosis; lung torsion; heterotaxy; right aortic arch; aberrant subclavian; malpositioned ETT; fractured bronchus; desquamative interstitial pneumonia; DIP lung; lung cancer staging; pancreatic laceration.

**Modality terms.** CT chest; chest CT; CT angiography; CTA chest; computed tomography chest; thoracic CT.

**Include keywords.** ct chest; chest ct; ct of the chest; ct thorax; ct angiography chest; cta chest; cta aorta; ct aorta; aortic ct; thoracic ct; contrast-enhanced ct chest; cect chest; chest ct scan; ct of the thorax.

**Exclude keywords.** ct abdomen; ct brain; ct head; ct pelvis; chest x-ray; chest xray; chest radiograph;  cxr ; mri; magnetic resonance; ultrasound; sonograph; pet scan; fdg; histopath; h&e; microscop; intraoperative; thoracoscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| aortic dissection | Aortic dissection |
| stanford type a | Aortic dissection type A |
| stanford type b | Aortic dissection type B |
| aortic aneurysm | Aortic aneurysm |
| penetrating aortic ulcer | Penetrating aortic ulcer |
| aspergillosis | Invasive aspergillosis |
| lymphoma chest | Thoracic lymphoma |
| hodgkin | Hodgkin lymphoma |

#### CXR

**Search keywords.** chest radiograph; chest X-ray; chest x-ray; chest x ray; CXR; plain chest film; chest roentgenogram; posteroanterior.

**Include keywords.** chest x-ray; chest x ray; chest radiograph; cxr; plain chest; chest film; pa view; ap view; posteroanterior; anteroposterior; plain radiograph.

**Exclude keywords.** computed tomography;  ct ; ct scan; ct chest; mri; magnetic resonance; pet scan; fdg; fluorodeoxyglucose; ultrasound; echocardiograph; sonograph; bronchoscop; endoscop; histopath; h&e; hematoxylin; microscop; patholog; intraoperative; angiograph; fluoroscop; mammogr; mammogram; tomosynthesis;  dbt ; craniocaudal; mediolateral;  mlo ;  cc view; breast imag; flowchart; flow chart; flow-chart;  diagram; schematic; algorithm; study design; protocol; workflow;  table ; timeline; time course; time line; perioperative; postoperative course;  bar graph; bar chart;  pie chart; x-ray aspect.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| dextrocardia | Dextrocardia |
| pneumocystis | Pneumocystis pneumonia |
| schwannoma | Schwannoma |

#### GI_FLUOROSCOPY

**Search keywords.** esophagram; barium swallow; upper GI series; upper gastrointestinal series; small bowel follow-through; small bowel follow through; enteroclysis; contrast enema; barium enema; fluoroscopic swallowing study; videofluoroscopic swallow study.

**Include keywords.** esophagram; oesophagram; barium swallow; upper gi series; upper gastrointestinal series; ugi series; small bowel follow-through; small bowel follow through; small bowel series; enteroclysis; contrast enema; barium enema; fluoroscopic swallowing study; videofluoroscopic swallow; modified barium swallow; fluoroscopic image; fluoroscopic spot image.

**Exclude keywords.** endoscopy; endoscopic; colonoscopy; gastroscopy; capsule endoscopy; intraoperative; surgical photograph; ct scan; computed tomography; mri; magnetic resonance; ultrasound; sonograph; pet/ct; pet scan; scintigraph; histopath; h&e; hematoxylin; microscop; flowchart; flow chart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| achalasia | Achalasia |
| esophageal perforation | Esophageal perforation |
| esophageal stricture | Esophageal stricture |
| malrotation | Intestinal malrotation |
| volvulus | Volvulus |
| hirschsprung | Hirschsprung disease |
| aspiration | Aspiration |

#### GU_FLUOROSCOPY

**Search keywords.** voiding cystourethrogram; voiding cystourethrography; VCUG; retrograde urethrogram; retrograde urethrography; cystogram; fluoroscopic cystography; hysterosalpingography; hysterosalpingogram; HSG; genitourinary fluoroscopy.

**Include keywords.** voiding cystourethrogram; voiding cystourethrography; vcug; micturating cystourethrogram; micturating cystourethrography; mcug; retrograde urethrogram; retrograde urethrography; ascending urethrogram; cystogram; cystography; hysterosalpingography; hysterosalpingogram; hsg; fluoroscopic image; fluoroscopic spot image.

**Exclude keywords.** cystoscopy; hysteroscopy; laparoscopy; endoscopy; intraoperative; surgical photograph; ct cystography; ct scan; computed tomography; mri; magnetic resonance; ultrasound; sonograph; pet/ct; pet scan; scintigraph; histopath; h&e; hematoxylin; microscop; flowchart; flow chart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| vesicoureteral reflux | Vesicoureteral reflux |
| posterior urethral valve | Posterior urethral valves |
| urethral stricture | Urethral stricture |
| bladder rupture | Bladder rupture |
| uterine anomaly | Mullerian anomaly |
| mullerian anomaly | Mullerian anomaly |
| tubal occlusion | Fallopian tube occlusion |

#### MAMMOGRAM

**Search keywords.** mammogram; mammography; breast imaging; digital breast tomosynthesis; DBT; screening mammogram; diagnostic mammogram.

**Include keywords.** mammogr; mammogram; breast imag; breast radiograph; craniocaudal; mediolateral oblique;  mlo ;  cc view;  ml view; tomosynthesis;  dbt ; screening mammogram; diagnostic mammogram; bilateral mammogr; unilateral mammogr; spot compression; magnification view;  rmlo ;  rcc ;  lmlo ;  lcc ; breast x-ray; breast radiolog; bi-rads; birads; microcalcification; macrocalcification; architectural distortion; breast density; fibroglandular.

**Exclude keywords.** breast ultrasound; breast us; sonogra; breast mri; magnetic resonance;  ct ; computed tomography; chest x-ray; chest xray; chest radiograph;  cxr ; chest film; posteroanterior; anteroposterior; pa view; ap view;  lung ;  pulmonary ; biopsy; histopath; microscop; patholog; h&e; hematoxylin; needle localization; wire localization; stereotactic biopsy; core biopsy; flowchart; flow chart;  diagram; schematic; algorithm;  table ; timeline; workflow.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| dcis | Ductal carcinoma in situ |
| fibroadenoma | Fibroadenoma |
| idc | Invasive ductal carcinoma |
| ilc | Invasive lobular carcinoma |
| phyllodes | Phyllodes tumor |

#### MRI_ABDOMEN

**Search keywords.** MRI abdomen; abdominal MRI; MR abdomen; magnetic resonance abdomen; magnetic resonance imaging abdomen; liver MRI; hepatic MRI; MRI liver; pancreatic MRI; MRI pancreas; MRCP; MR cholangiopancreatography; MR enterography; magnetic resonance enterography; bowel MRI; small bowel MRI; rectal MRI; MRI rectum.

**Include keywords.** mri abdomen; abdominal mri; mr abdomen; mri of the abdomen; mrcp; mr cholangiopancreatography; liver mri; hepatic mri; mri liver; mri of the liver; rectal mri; mri rectum; mri of the rectum; mri pancreas; pancreatic mri; body mri; magnetic resonance imaging abdomen; contrast-enhanced mri abdomen; gadolinium abdomen; hepatobiliary phase; primovist; eovist; t2-weighted abdomen; diffusion-weighted liver; dwi liver; dwi abdomen; mr enterography; mri enterography; magnetic resonance enterography; bowel mri; small bowel mri; crohn mri; ibd mri; mr urogram; mr urography; magnetic resonance urogram; magnetic resonance urography; mru.

**Exclude keywords.** ct abdomen; ct scan abdomen; computed tomography abdomen; mri brain; brain mri; mri spine; spine mri; mri knee; mri shoulder; mri hip; mri pelvis; mri prostate; mri uterus; mri cervix; mri bladder; chest mri; mri chest; cardiac mri; ultrasound; sonograph; pet scan; scintigraph; chest x-ray; radiograph; histopath; h&e; microscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| hcc | Hepatocellular carcinoma |
| hepatocellular carcinoma | Hepatocellular carcinoma |
| fnl | Focal nodular hyperplasia |
| focal nodular hyperplasia | Focal nodular hyperplasia |
| hepatic adenoma | Hepatic adenoma |
| ipmn | IPMN |
| intraductal papillary | IPMN |
| cholangiocarcinoma | Cholangiocarcinoma |
| psc | Primary sclerosing cholangitis |
| primary sclerosing cholangitis | Primary sclerosing cholangitis |
| choledocholithiasis | Choledocholithiasis |
| rectal cancer | Rectal carcinoma |
| rectal carcinoma | Rectal carcinoma |
| crohn | Crohn disease |

#### MRI_BRAIN

**Search keywords.** brain MRI; MRI brain; cerebral MRI; brain magnetic resonance; cerebral magnetic resonance imaging; MRA brain; brain MR angiography; diffusion weighted imaging brain; FLAIR brain; brain MR imaging; intracranial MRI; cranial MRI.

**Include keywords.** mri brain; mri of the brain; mri of brain; brain mri; cerebral mri; cranial mri; intracranial mri; brain mr imaging; brain mr image; brain magnetic resonance; cerebral magnetic resonance; mra brain; mra of the brain; brain mra; intracranial mra; intracranial mr angiograph; mr venograph; mrv brain; flair;  swi ; swi sequence; susceptibility-weighted; susceptibility weighted; dwi brain; diffusion brain; diffusion-weighted brain; adc map brain; apparent diffusion brain; mri cerebellum; mri brainstem; mri temporal lobe; mri frontal lobe; mri hippocampus; mri basal ganglia; mri thalamus; mri corpus callosum; mri ventricle; mri white matter; pituitary mri; sellar mri; mri pituitary; acoustic neuroma mri; vestibular schwannoma mri.

**Exclude keywords.** spine mri; mri spine; spinal mri; spinal cord mri; lumbar mri; cervical spine mri; thoracic spine mri; mri lumbar; mri cervical spine; mri abdomen; abdominal mri; liver mri; mrcp; mri pelvis; pelvic mri; prostate mri; pi-rads; pirads; neck mri; mri neck; parotid mri; thyroid mri; breast mri; mri breast; cardiac mri; heart mri; knee mri; shoulder mri; hip mri; stir; ct brain; brain ct; ct head; head ct; computed tomography brain; ncct brain; pet scan; fdg; spect; ultrasound; sonograph; echocardiograph; fluoroscop; x-ray; radiograph; mammogr; mammogram; histopath; h&e; hematoxylin; microscop; flowchart; flow chart; flow-chart;  diagram; schematic; algorithm; study design; protocol; workflow;  table ; bar graph; bar chart; pie chart.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  avm  | Arteriovenous malformation |
|  cva  | Acute ischemic stroke |
|  gbm  | Glioblastoma |
|  ms  | Multiple sclerosis |
|  pml  | Progressive multifocal leukoencephalopathy |
|  pres  | Posterior reversible encephalopathy syndrome |
| acoustic neuroma | Vestibular schwannoma |
| acute ischemic stroke | Acute ischemic stroke |
| arteriovenous malformation | Arteriovenous malformation |
| brain metastasis | Brain metastasis |
| cavernoma | Cavernous malformation |
| cavernous malformation | Cavernous malformation |
| cerebral cavernous | Cavernous malformation |
| cerebral infarct | Acute ischemic stroke |
| cerebral infarction | Acute ischemic stroke |
| cerebral metastasis | Brain metastasis |
| craniopharyngioma | Craniopharyngioma |
| ependymoma | Ependymoma |
| glioblastoma | Glioblastoma |
| glioblastoma multiforme | Glioblastoma |
| medulloblastoma | Medulloblastoma |
| meningioma | Meningioma |
| metastasis | Brain metastasis |
| multiple sclerosis | Multiple sclerosis |
| neurocysticercosis | Neurocysticercosis |
| pituitary adenoma | Pituitary adenoma |
| posterior reversible encephalopathy | Posterior reversible encephalopathy syndrome |
| progressive multifocal leukoencephalopathy | Progressive multifocal leukoencephalopathy |
| vestibular schwannoma | Vestibular schwannoma |

#### MRI_MSK

**Search keywords.** knee MRI; shoulder MRI; hip MRI; ankle MRI; wrist MRI; musculoskeletal MRI; MSK MRI; MRI knee ligament; MRI rotator cuff; MRI meniscus; MRI tendon; MRI labrum; MRI soft tissue; magnetic resonance knee; magnetic resonance shoulder.

**Diagnosis terms.** ACL injury; anterior cruciate ligament tear; meniscal tear; rotator cuff tear; labral tear; Achilles tendon; plantar fasciitis; avascular necrosis; subchondral insufficiency; extensor mechanism; biceps tendon; gluteal tendon; hamstring tendon; peroneal tendon; ankle ligament; cartilage osteoarthritis.

**Modality terms.** MRI; magnetic resonance imaging; knee MRI; shoulder MRI; hip MRI; ankle MRI; musculoskeletal MRI.

**Include keywords.** mri knee; knee mri; mr knee; magnetic resonance knee; mri shoulder; shoulder mri; mr shoulder; mri hip; hip mri; mr hip; mri ankle; ankle mri; mr ankle; mri wrist; wrist mri; mri tendon; mri ligament; mri labrum; mri soft tissue; musculoskeletal mri; msk mri; t2-weighted; proton density; fat-suppressed mri; stir sequence msk.

**Exclude keywords.** mri brain; brain mri; mri head; head mri; mri spine; spine mri; mri cervical; mri lumbar; mri abdomen; mri pelvis; mri chest; mri cardiac; ct scan;  ct ; ultrasound; sonograph; x-ray; radiograph; plain film; pet scan; bone scan; histopath; h&e; microscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  acl  | ACL injury |
| anterior cruciate | ACL injury |
|  pcl  | PCL injury |
| posterior cruciate | PCL injury |
| rotator cuff | Rotator cuff tear |
| meniscal tear | Meniscal tear |
| labral tear | Labral tear |
| avascular necrosis | Avascular necrosis |
|  avn  | Avascular necrosis |
| hamstring | Hamstring tendon injury |
| achilles | Achilles tendon pathology |
| plantar fasci | Plantar fasciitis |

#### MRI_NEURO_SPINE

**Search keywords.** spine fracture CT MRI case; skull fracture CT case report; spinal cord demyelination MRI; epidural hematoma MRI CT; epidural abscess MRI; spinal metastasis MRI; Guillain-Barre MRI; optic neuritis MRI; fungal sinusitis CT MRI; atlanto-occipital dislocation CT.

**Diagnosis terms.** skull fracture; spine fracture; cervical fracture; atlanto-occipital dislocation; epidural hematoma; epidural abscess; spinal subdural hematoma; bone metastasis spine; epidural tumor; Guillain-Barre; demyelination spinal cord; optic neuritis; fungal sinusitis.

**Modality terms.** spine MRI; brain MRI; MRI spine; MRI brain; CT skull; spinal CT; CT spine; magnetic resonance spine.

**Include keywords.** mri spine; spine mri; spinal mri; mr spine; ct spine; spine ct; spinal ct; mri cervical; cervical mri; mri lumbar; lumbar mri; mri thoracic spine; thoracic spine mri; ct skull; skull ct; ct head bone; bone window; mri brain; brain mri; ct sinuses; sinus ct; facial ct; spinal cord mri; mri cord.

**Exclude keywords.** ct chest; ct abdomen; ct pelvis; chest x-ray; chest radiograph; ultrasound; sonograph; pet scan; bone scan; fdg; histopath; h&e; microscop; flowchart; diagram; schematic;  table ; knee mri; shoulder mri; hip mri; ankle mri; musculoskeletal mri.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| skull fracture | Acute skull fracture |
| spine fracture | Acute spine fracture |
| cervical fracture | Cervical fracture |
| epidural hematoma | Epidural hematoma |
| epidural abscess | Epidural abscess |
| guillan-barre | Guillain-Barre syndrome |
| guillain barre | Guillain-Barre syndrome |
| aidp | Guillain-Barre syndrome |
| demyelination | Acute demyelination |
| optic neuritis | Acute optic neuritis |
| fungal sinusitis | Invasive fungal sinusitis |
| bone metastasis spine | Bone metastasis in the spine |

#### MRI_PELVIS

**Search keywords.** MRI pelvis; pelvic MRI; MR pelvis; magnetic resonance pelvis; magnetic resonance imaging pelvis; MRI prostate; prostate MRI; multiparametric prostate MRI; mpMRI prostate; MRI bladder; bladder MRI; MRI uterus; uterine MRI; MRI cervix; cervical MRI; MRI ovary; ovarian MRI; adnexal MRI; female pelvic MRI.

**Include keywords.** mri pelvis; pelvic mri; mr pelvis; mri of the pelvis; mri prostate; prostate mri; mpmri; multiparametric mri; pi-rads; pirads; mri uterus; uterine mri; mri of the uterus; mri cervix; cervical mri; mri of the cervix; mri bladder; bladder mri; mri ovary; ovarian mri; magnetic resonance pelvis; magnetic resonance imaging pelvis; gadolinium pelvis; t2-weighted pelvis; diffusion-weighted pelvis; dwi pelvis.

**Exclude keywords.** ct pelvis; ct scan pelvis; computed tomography pelvis; mri brain; brain mri; mri spine; spine mri; mri knee; mri shoulder; mri hip; mri abdomen; abdominal mri; mri liver; chest mri; mri chest; ultrasound; sonograph; pet scan; scintigraph; chest x-ray; radiograph; plain film; histopath; h&e; microscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| prostate cancer | Prostate carcinoma |
| prostate carcinoma | Prostate carcinoma |
| pi-rads | Prostate carcinoma |
| leiomyoma | Uterine leiomyoma |
| fibroid | Uterine leiomyoma |
| leiomyosarcoma | Uterine leiomyosarcoma |
| endometrial cancer | Endometrial carcinoma |
| endometrial carcinoma | Endometrial carcinoma |
| cervical cancer | Cervical carcinoma |
| cervical carcinoma | Cervical carcinoma |
| endometrioma | Ovarian endometrioma |
| ovarian cancer | Ovarian carcinoma |
| bladder cancer | Bladder carcinoma |
| urothelial carcinoma | Bladder carcinoma |
| placenta accreta | Placenta accreta spectrum |
| mullerian | Mullerian anomaly |

#### MRI_SPINE

**Search keywords.** spine MRI; spinal MRI; lumbar MRI; cervical spine MRI; thoracic spine MRI; MRI lumbar spine; MRI cervical spine; spinal cord MRI; vertebral MRI; lumbosacral MRI.

**Include keywords.** lumbar mri; mri lumbar; mri of the lumbar; lumbar spine mri; mri lumbar spine; lumbosacral mri; mri lumbosacral; cervical spine mri; mri cervical spine; mri of the cervical spine; cervical spine magnetic resonance; thoracic spine mri; mri thoracic spine; mri of the thoracic spine; spine mri; mri spine; spinal mri; mri of the spine; spinal cord mri; mri spinal cord; mri of the spinal cord; vertebral mri; mri vertebra; mri intervertebral; disc mri; mri disc; intervertebral disc mri; mri herniation; disc herniation mri; mri conus; mri cauda equina; mri sacrum; mri epidural; epidural mri; stir.

**Exclude keywords.** mri brain; brain mri; cerebral mri; cranial mri; flair;  swi ; swi sequence; susceptibility-weighted; susceptibility weighted; dwi brain; diffusion brain; neck mri; mri neck; soft tissue neck mri; parotid mri; thyroid mri; carotid mri; mri abdomen; abdominal mri; liver mri; mrcp; mri pelvis; pelvic mri; prostate mri; pi-rads; pirads; breast mri; mri breast; cardiac mri; heart mri; knee mri; shoulder mri; hip mri; ct spine; spine ct; computed tomography spine; ct lumbar; ct cervical spine; ct thoracic spine; ct myelograph; pet scan; fdg; ultrasound; sonograph; x-ray; radiograph; plain film; fluoroscop; histopath; h&e; hematoxylin; microscop; flowchart; flow chart; flow-chart;  diagram; schematic; algorithm; study design; protocol; workflow;  table ; bar graph; bar chart; pie chart.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  csm  | Cervical spondylotic myelopathy |
|  opll  | Ossification of posterior longitudinal ligament |
| astrocytoma | Spinal cord astrocytoma |
| cervical disc | Cervical disc herniation |
| cervical spinal stenosis | Cervical spinal stenosis |
| chiari | Chiari malformation |
| disc extrusion | Disc herniation |
| disc herniation | Disc herniation |
| disc protrusion | Disc herniation |
| ependymoma | Spinal ependymoma |
| epidural abscess | Spinal epidural abscess |
| hemangioma | Vertebral hemangioma |
| lumbar disc | Lumbar disc herniation |
| lumbar spinal stenosis | Lumbar spinal stenosis |
| ossification of posterior longitudinal ligament | Ossification of posterior longitudinal ligament |
| spinal cord infarct | Spinal cord infarction |
| spinal epidural abscess | Spinal epidural abscess |
| spinal meningioma | Spinal meningioma |
| spinal metastases | Spinal metastasis |
| spinal metastasis | Spinal metastasis |
| spinal stenosis | Spinal stenosis |
| spondylodiscitis | Spondylodiscitis |
| spondylolisthesis | Spondylolisthesis |
| spondylotic myelopathy | Cervical spondylotic myelopathy |
| syringomyelia | Syringomyelia |
| syrinx | Syringomyelia |
| transverse myelitis | Transverse myelitis |
| vertebral hemangioma | Vertebral hemangioma |
| vertebral osteomyelitis | Vertebral osteomyelitis |

#### MSK_CT

**Search keywords.** musculoskeletal CT; bone CT; CT knee; CT shoulder; CT hip; CT ankle; CT wrist; CT elbow; CT foot; CT hand.

**Include keywords.** musculoskeletal ct; bone ct; ct knee; ct shoulder; ct hip; ct ankle; ct wrist; ct elbow; ct foot; ct hand; ct of the joint.

**Exclude keywords.** mri; magnetic resonance; ultrasound; sonograph; radiograph; x-ray; pet/ct; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### MSK_ULTRASOUND

**Search keywords.** musculoskeletal ultrasound; musculoskeletal ultrasonography; tendon ultrasound; tendon ultrasonography; joint ultrasound; joint ultrasonography; muscle ultrasound; muscle ultrasonography; shoulder ultrasound; peripheral nerve ultrasound; peripheral nerve sonography; power Doppler synovitis; dynamic ultrasound.

**Include keywords.** musculoskeletal ultrasound; musculoskeletal ultrasonography; tendon ultrasound; tendon ultrasonography; joint ultrasound; joint ultrasonography; muscle ultrasound; muscle ultrasonography; shoulder ultrasound; peripheral nerve ultrasound; peripheral nerve sonography; dynamic ultrasound; ultrasound image; ultrasonographic; sonographic; sonogram; power doppler; color doppler; colour doppler; us scan; ultrasound-guided; ultrasound guided.

**Exclude keywords.** mri; magnetic resonance; ct scan; computed tomography; radiograph; x-ray; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### MSK_XRAY

**Search keywords.** musculoskeletal radiograph; skeletal radiograph; bone radiograph; orthopedic radiograph; fracture radiograph; plain radiograph fracture; joint X-ray; skeletal X-ray; CT fracture; CT musculoskeletal; cervical spine fracture; lumbar spine radiograph; hip fracture radiograph; knee radiograph; ankle radiograph; wrist radiograph; shoulder radiograph; foot radiograph.

**Diagnosis terms.** fracture; dislocation; arthropathy; arthritis; calcific tendinosis; calcium pyrophosphate; CPPD; spondylolysis; cervical fracture; hip fracture; ankle fracture; foot fracture; soft tissue sarcoma; enchondroma; non-ossifying fibroma; fibrous dysplasia; lipoma soft tissue; myxoma; benign bone tumor.

**Modality terms.** radiograph; X-ray; plain film; plain radiograph; CT bone; skeletal radiograph.

**Include keywords.** plain radiograph; plain x-ray; plain film; anteroposterior view; ap view; lateral view; weight-bearing radiograph; standing radiograph; ct scan bone; ct bone; bone window; skeletal survey; bone survey; radiograph shows; x-ray shows; x-ray demonstrates.

**Exclude keywords.** chest x-ray; chest radiograph; cxr;  pa view; ct chest; ct abdomen; ct brain; ct head; mri; magnetic resonance; ultrasound; sonograph; pet scan; bone scan; scintigraph; histopath; h&e; microscop; intraoperative; arthroscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  acl  | ACL injury |
| anterior cruciate | ACL injury |
| rotator cuff | Rotator cuff tear |
| meniscal tear | Meniscal tear |
| cppd | Calcium pyrophosphate disease |
|  hadd  | Calcific tendinosis |
| calcific tendinitis | Calcific tendinosis |
| spondylolysis | Lumbar spondylolysis |
| scfe | Slipped capital femoral epiphysis |
| perthes | Perthes disease |
| avascular necrosis | Avascular necrosis |
|  avn  | Avascular necrosis |

#### NM_NUCLEAR

**Search keywords.** FDG PET CT case report; PET scan case report; HIDA scan case report; hepatobiliary scintigraphy; thyroid scintigraphy case; parathyroid scintigraphy; DOTATATE PET case; PSMA PET case report; bone scintigraphy case; nuclear medicine case report; SPECT CT case report; PYP scintigraphy cardiac amyloid; FDG PET sarcoidosis; FDG PET lymphoma.

**Diagnosis terms.** cardiac sarcoidosis; cardiac amyloidosis; parathyroid adenoma; cholecystitis; biliary atresia; thyroid nodule; NET metastases; PSMA; DOTATATE; fever of unknown origin; lymphoma; head and neck cancer; colon polyp; melanoma; sentinel lymph node melanoma; DMSA scintigraphy; reactive marrow; lung cancer staging; FDG PET staging.

**Modality terms.** FDG PET; PET CT; PET-CT; HIDA; scintigraphy; SPECT; nuclear medicine; DOTATATE; PSMA PET.

**Include keywords.** fdg pet; pet-ct; pet ct; pet scan; hida scan; hepatobiliary scintigraphy; cholescintigraphy; thyroid scan; thyroid scintigraphy; thyroid uptake; parathyroid scan; parathyroid scintigraphy; sestamibi; dotatate; dotatoc; gallium; ga-68; psma pet; psma scan; pyp scan; pyp scintigraphy; technetium pyrophosphate; bone scan; bone scintigraphy; spect; spect/ct; spect ct; nuclear medicine; scintigraphy; dmsa scan; mag3 scan; renography.

**Exclude keywords.** ct chest; ct abdomen; ct brain; mri; magnetic resonance; ultrasound; sonograph; echocardiograph; chest x-ray; chest radiograph; plain film; histopath; h&e; microscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| fdg | FDG PET |
| sarcoidosis | Cardiac sarcoidosis |
| amyloid | Cardiac amyloidosis |
| thyroid nodule | Thyroid nodule |
| graves | Graves disease |
| cholecystitis | Acute cholecystitis |
| biliary atresia | Biliary atresia |

#### OBSTETRIC_ULTRASOUND

**Search keywords.** obstetric ultrasound; fetal ultrasound; prenatal ultrasound; pregnancy ultrasound; placental ultrasound; antenatal sonography.

**Include keywords.** obstetric ultrasound; fetal ultrasound; prenatal ultrasound; pregnancy ultrasound; placental ultrasound; antenatal sonography; fetal sonography.

**Exclude keywords.** fetal mri; placental mri; computed tomography; ct scan; radiograph; x-ray; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### US_ABDOMEN

**Search keywords.** abdominal ultrasound; ultrasound abdomen; abdominal sonography; hepatic ultrasound; liver ultrasound; renal ultrasound; ultrasound liver; ultrasound kidney; abdominal US; upper abdominal ultrasound.

**Include keywords.** abdominal ultrasound; ultrasound abdomen; abdominal sonography; abdominal us; us abdomen; sonography abdomen; upper abdominal ultrasound; upper abdominal sonography; hepatic ultrasound; liver ultrasound; ultrasound liver; hepatic sonography; us liver; liver sonogram; gallbladder ultrasound; ultrasound gallbladder; biliary ultrasound; choledochal ultrasound; renal ultrasound; kidney ultrasound; ultrasound kidney; renal sonography; us kidney; kidney sonogram; splenic ultrasound; spleen ultrasound; pancreatic ultrasound; hyperechoic; hypoechoic; anechoic; isoechoic; heterogeneous echogenicity; acoustic shadow.

**Exclude keywords.** ct abdomen; abdominal ct; computed tomography abdomen; ct scan abdomen; ct of the abdomen; cect abdomen; contrast-enhanced ct; portal venous phase; mri abdomen; abdominal mri; magnetic resonance abdomen; liver mri; mrcp; magnetic resonance cholangiopancreatography; abdominal x-ray; plain abdominal; kub radiograph; abdominal radiograph; pet scan; pet-ct; fdg; spect; obstetric ultrasound; fetal ultrasound; transvaginal ultrasound; breast ultrasound; breast us; breast sonography; thyroid ultrasound; thyroid us; ti-rads; carotid ultrasound; carotid doppler; vascular ultrasound; transrectal ultrasound; trus; prostate ultrasound; pelvic ultrasound; transvaginal; endovaginal; echocardiograph; cardiac ultrasound; transthoracic echo; transesophageal echo;  tee ;  tte ; endoscopic ultrasound;  eus ; endosonography; histopath; h&e; hematoxylin; microscop; flowchart; flow chart;  diagram; schematic; algorithm; study design;  table ; bar graph.

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  cbd stone | Choledocholithiasis |
|  hcc  | Hepatocellular carcinoma |
|  rcc  | Renal cell carcinoma |
| acute cholecystitis | Acute cholecystitis |
| cholecystitis | Acute cholecystitis |
| choledocholithiasis | Choledocholithiasis |
| cholelithiasis | Cholelithiasis |
| common bile duct stone | Choledocholithiasis |
| fatty liver | Hepatic steatosis |
| gallstone | Cholelithiasis |
| gallstones | Cholelithiasis |
| hepatic abscess | Hepatic abscess |
| hepatic hemangioma | Hepatic hemangioma |
| hepatic steatosis | Hepatic steatosis |
| hepatocellular carcinoma | Hepatocellular carcinoma |
| hydronephrosis | Hydronephrosis |
| kidney stone | Nephrolithiasis |
| liver hemangioma | Hepatic hemangioma |
| nephrolithiasis | Nephrolithiasis |
| pyogenic liver abscess | Hepatic abscess |
| renal calculus | Nephrolithiasis |
| renal cell carcinoma | Renal cell carcinoma |
| splenic infarct | Splenic infarct |
| splenic infarction | Splenic infarct |

#### US_GYN_TRANS

**Search keywords.** ovarian cyst ultrasound case report; gynecologic ultrasound case; testicular ultrasound case report; scrotal ultrasound case; transplant Doppler ultrasound case; renal transplant ultrasound; hepatic transplant ultrasound; epididymo-orchitis ultrasound; subchorionic hemorrhage ultrasound; ovarian torsion ultrasound.

**Diagnosis terms.** ovarian cyst; hemorrhagic cyst; ovarian malignancy; sex cord stromal tumor; epididymo-orchitis; testicular rupture; testicular hematoma; subchorionic hemorrhage; transplant hepatic artery stenosis; transplant renal vein thrombosis; pancreatic transplant; soft tissue lipoma; congenital uterine anomaly; uterine anomaly; Mullerian anomaly; germinal matrix hemorrhage; multicystic dysplastic kidney; Fournier gangrene; perianal fistula; congenital duodenal obstruction; hip dysplasia infant.

**Modality terms.** ultrasound; sonography; Doppler; pelvic ultrasound; scrotal ultrasound; transvaginal ultrasound.

**Include keywords.** pelvic ultrasound; transvaginal ultrasound; transabdominal ultrasound; gynecologic ultrasound; obstetric ultrasound; scrotal ultrasound; testicular ultrasound; scrotal sonograph; transplant doppler; renal transplant ultrasound; hepatic transplant ultrasound; liver transplant doppler; doppler ultrasound transplant; soft tissue ultrasound; superficial ultrasound.

**Exclude keywords.** ct scan; mri; magnetic resonance; chest x-ray; chest radiograph; pet scan; bone scan; abdominal ultrasound liver; hepatic ultrasound; carotid doppler; vascular doppler; histopath; h&e; microscop; flowchart; diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
| epididymo-orchitis | Acute epididymo-orchitis |
| epididymoorchitis | Acute epididymo-orchitis |
| testicular torsion | Testicular torsion |
| testicular rupture | Testicular rupture |
| ovarian cyst | Ovarian cyst |
| hemorrhagic cyst | Ovarian hemorrhagic cyst |
| subchorionic | Subchorionic hemorrhage |
| ovarian malignancy | Ovarian malignant neoplasm |
| sex cord stromal | Ovarian sex cord stromal tumor |
| hepatic artery stenosis | Transplant hepatic artery stenosis |
| renal vein thrombosis | Transplant renal vein thrombosis |
| pancreatic transplant | Pancreatic transplant |

#### US_PELVIS

**Search keywords.** pelvic ultrasound; ultrasound pelvis; pelvic sonography; transvaginal ultrasound; transrectal ultrasound; TRUS; uterine ultrasound; ovarian ultrasound; prostate ultrasound; endovaginal ultrasound; pelvic US.

**Include keywords.** pelvic ultrasound; ultrasound pelvis; pelvic sonography; pelvic us; us pelvis; pelvic sonogram; transvaginal ultrasound; transvaginal sonography; endovaginal ultrasound; tvs; tv ultrasound; transrectal ultrasound; trus; prostate ultrasound; ultrasound prostate; uterine ultrasound; uterus ultrasound; ultrasound uterus; ovarian ultrasound; ovary ultrasound; adnexal ultrasound; endometrial thickness; endometrium ultrasound; ovarian cyst; endometriosis; uterine fibroid; adenomyosis; endometrioma.

**Exclude keywords.** obstetric ultrasound; fetal ultrasound; pregnancy ultrasound; gestational sac; fetal pole; fetal heart;  bpd ;  crl ; amniotic fluid; first trimester; second trimester; third trimester; gravid; pregnant; ct pelvis; pelvic ct; computed tomography pelvis; mri pelvis; pelvic mri; magnetic resonance pelvis;  pi-rads ; pirads; abdominal ultrasound; hepatic ultrasound; renal ultrasound; breast ultrasound; breast us; thyroid ultrasound; thyroid us; carotid ultrasound; vascular ultrasound; echocardiograph; cardiac ultrasound; histopath; h&e; microscop; hysteroscopy; laparoscopy; colposcopy; flowchart;  diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  bph  | Benign prostatic hyperplasia |
|  myoma  | Uterine fibroid |
| adenomyosis | Adenomyosis |
| benign prostatic hyperplasia | Benign prostatic hyperplasia |
| ectopic pregnancy | Ectopic pregnancy |
| endometrioma | Endometrioma |
| endometriosis | Endometriosis |
| leiomyoma | Uterine fibroid |
| ovarian cyst | Ovarian cyst |
| ovarian cystadenoma | Ovarian cystadenoma |
| ovarian torsion | Ovarian torsion |
| prostate cancer | Prostate cancer |
| prostate carcinoma | Prostate cancer |
| prostatic carcinoma | Prostate cancer |
| uterine fibroid | Uterine fibroid |

#### US_SUPERFICIAL

**Search keywords.** thyroid ultrasound; thyroid sonography; neck ultrasound; neck sonography; pleural ultrasound; pleural sonography; salivary gland ultrasound; parotid ultrasound.

**Include keywords.** thyroid ultrasound; thyroid sonography; thyroid us; ultrasound thyroid; sonography thyroid; neck ultrasound; neck sonography; cervical ultrasound; cervical sonography; pleural ultrasound; pleural sonography; salivary gland ultrasound; salivary gland sonography; parotid ultrasound; parotid sonography; superficial ultrasound; superficial sonography; point-of-care neck.

**Exclude keywords.** ct neck; mri neck; ct chest; mri chest; carotid doppler; carotid ultrasound; abdominal ultrasound; pelvic ultrasound; echocardiograph; cardiac ultrasound; obstetric ultrasound; fetal ultrasound; musculoskeletal ultrasound; histopath; h&e; hematoxylin; microscop; gross specimen; flowchart; flow chart; diagram; schematic; algorithm;  table ; intraoperative; surgical photograph; endoscopy.

#### US_VASCULAR

**Search keywords.** carotid ultrasound; carotid doppler; vascular ultrasound; doppler ultrasound; venous ultrasound; arterial ultrasound; deep vein thrombosis ultrasound; DVT ultrasound; carotid duplex; peripheral vascular ultrasound.

**Include keywords.** carotid ultrasound; carotid doppler; carotid duplex; ultrasound carotid; doppler carotid; carotid sonography; venous ultrasound; venous doppler; deep vein thrombosis;  dvt ; lower extremity doppler; upper extremity doppler; compression ultrasound; arterial doppler; arterial ultrasound; peripheral arterial; lower extremity arterial; renal artery doppler; spectral doppler; color doppler; power doppler; peak systolic velocity;  psv ; end-diastolic velocity; resistive index;  ri ; pulsatility index; stenosis; occlusion; thrombus; plaque; intima-media thickness;  imt .

**Exclude keywords.** echocardiograph; transthoracic echo; transesophageal echo;  tee ;  tte ; cardiac ultrasound;  cta ; ct angiography; computed tomography angiography;  mra ; mr angiography; magnetic resonance angiography; ct aortogram; mri aorta; abdominal ultrasound; hepatic ultrasound; renal ultrasound; obstetric ultrasound; fetal ultrasound; breast ultrasound; breast us; thyroid ultrasound; thyroid us; pelvic ultrasound; transvaginal; thyroid doppler; liver doppler; renal doppler; testicular doppler; scrotal doppler; angiography; catheter angiogram; venography; histopath; microscop; flowchart;  diagram; schematic;  table .

**Diagnosis normalization.**

| Input | Normalized or configured value |
|---|---|
|  aaa  | Abdominal aortic aneurysm |
|  dvt  | Deep vein thrombosis |
|  pad  | Peripheral arterial disease |
|  pe  | Pulmonary embolism |
| abdominal aortic aneurysm | Abdominal aortic aneurysm |
| carotid artery stenosis | Carotid stenosis |
| carotid stenosis | Carotid stenosis |
| deep vein thrombosis | Deep vein thrombosis |
| peripheral arterial disease | Peripheral arterial disease |
| pulmonary embolism | Pulmonary embolism |
| renal artery stenosis | Renal artery stenosis |
| subclavian steal syndrome | Subclavian steal syndrome |

