## BIBAGENT: An Agentic Framework for Traceable Miscitation Detection in Scientific Literature

Peiran Li1?  Fangzhou Lin 13  Shuo Xing 1  Xiang Zheng?  Xi Hong2  Jiashuo Sun 4 Zhengzhong Tu 1 Chaoqun Ni2

## Abstract

Citations are the bedrock of scientific authority, yet their integrity is compromised by widespread miscitations: ranging from nuanced distortions to fabricatedreferences.Systematiccitationverificationis currently unfeasible;manual review cannot scale to modern publishingvolumes,while existing automated tools are restricted by abstract-only analysis or small-scale,domain-specific datasets in part due to the"paywall barrier"of full-text access.We introduce BIBAGENT,a scalable,endto-end agenticframeworkfor automated citation verification. BIBAGENT integrates retrieval, reasoning, and adaptive evidence aggregation, applying distinct strategies for accessible and paywalled sources. For paywalled references, it leverages a novelEvidenceCommitteemechanism that infers citationvalidityvia downstreamcitation consensus. To support systematic evaluation, we contributea5-categoryMiscitationTaxonomyand MISCITEBENCH, a massive cross-disciplinary benchmarkcomprising6,350miscitationsamples spanning 254 fields. Our results demonstrate that BIBAGENT outperforms state-of-the-art Large Language Model (LLM) baselines in citation verification accuracy and interpretability, providing scalable, transparent detection of citation misalignments across the scientific literature.

## 1. Introduction

Citations are central to scientific communication, shaping howknowledge claims are established, credit is assigned, andresearch is evaluated.Assuch,citations are widely treatedasreliableindicatorsofconceptualconnectionand researchimpact,underpinningformal researchevaluations

Texas A&amp;M University²University of Wisconsin-Madison 3Worcester Polytechnic Institute 4University of Illinois UrbanaChampaign. Correspondence to: Peiran Li &lt;lipeiran @tamu.edu&gt;, Chaoqun Ni&lt;chaoqun.ni@wisc.edu&gt;.

for hiring, promotion, and funding (Waltman, 2016). This system,however, rests on the assumption that citations are accurate.Yet, a growing body of scholarship reveals that citationpractices areofteninconsistent,fawed,orstrategically manipulated (Simkin &amp; Roychowdhury, 2003; Wilhite &amp; Fong,2012; Greenberg, 2009). This phenomenon, miscitation,occurswhencitedsourcesaredistorted,fabricated, or taken out of context.The scale is alarming: studies show high rates of inaccuracy,with one analysis finding 39%ofsampledbiomedicalcitationswereinaccurate(Sarol et al., 2024), and other manual audits reporting misquotation rates between 10%-25%, depending on the field (De Lacey et al.,1985;Jergas &amp;Baethge,2015;Rekdal,2014).This is notjust accidental;thehigh-stakesevaluationsystemhas spurred deliberate manipulation, including coercive citation (Wilhite &amp; Fong,2012), citation cartels (Secchi,2022),and black market schemes (Chawla, 2024). This long-standing problemisnowexacerbatedby theemergenceofgenerative AI. Large Language Models (LLMs)introduce new risks by producing"hallucinatedcitations",fabricated ordistorted references,andtheirintegrationintoscholarlyworkflows threatenswidespread,systematicerrors(Walters&amp;Wilder, 2023; Liang et al., 2024; Ra0 et al.,2025). Miscitations have severe consequences: they distort the evidentiary basis of claims, propagate inaccuracies, and erode the reliability of citation-based metrics, thereby undermining the integrity of thescientificrecordand thefairnessoftheresearchecosystem.

Yet, detecting miscitations is inherently challenging. Even for expert reviewers and editors,verifying citation accuracy requires closereadinganddetailedfamiliaritywithboth the citing and cited texts,including the ability to assess whether the citation faithfully represents the original work in content, context, and intent. Given that the average scientific article cites more than 45references (Daiet al.,2021),and that suchassessmentsdemandconsiderableexpertiseandtime, manual verification is not scalable.The challenge isfurther compounded by the fact that a substantial portion of scientific literature is behind paywalls or otherwise inaccessible, making it impossible for reviewers to fully evaluate the cited sources.

Automated approachesbased onnaturallanguageprocess-



--- Page Break ---



ing(NLP)offerpromise,butexistingsystemsfacethree fundamental limitations. First, the definition of "miscitation" remains conceptually ambiguous. Traditional NLP approaches have historically oscillated between coarse-grained sentiment analysis (Teufel et al.,2006） and binary factchecking (Athar &amp; Teufel, 2012). These frameworks ignore nuanced errors,such as scope extrapolation or evidence characterization,in which a citation may be technically "supportive"but methodologically misrepresented. Second, sibility barrier."High-performing benchmarks like (Wadden et al., 2020) rely primarily on abstracts, yet the evidence required to identify contradictions often resides in other parts of scientific articles, such as experimental tables or appendices. Furthermore, since much of the scientific record remains behind paywalls, AI systems frequently default to access the full text. Finally, the emergence of LLMs has inmirror the user's claims rather than rigorously challenging themagainsttheevidence(Weietal.,2024).Collectively, these barriers,compounded by a scarcity of labeled data and disciplinary heterogeneity, have limited research to small, proprietary datasets, leaving the scientific community without a robust, generalizable system for maintaining citation integrity in an era of AI-augmented writing.

To bridge these gaps, we present B1BAGENT, a comprehensiveframeworkdesignedtoevaluatethealignmentbetween citingclaimsandcitedpapersforresearchintegrity.Unlikesome prior approaches that treatmiscitation detection as a single classification task,BIBAGENT recognizes that miscitation detection is a multi-layered investigative process that must adapt to varying levels of data accessibility. For accessible sources (i.e.,the full text of a cited paper is accessible),weintroducetheAccessibleCitedSourceVerifier (ACsV), which uses an adaptive multi-stage architecture. It moves from efficient bi-encoder retrieval to deep, Large Language Model (LLM)-driven verification only when ambiguity arises. This design ensures traceability and reduces token consumption by 79.4%without compromising the 100%detectionrate.

Themostsignificant departurefrom existingmethodologies lies in our treatment of the"Inaccessibility Barrier"through theInaccessibleCitedSourceVerifier(ICsV),incasethe full text of a cited paper is inaccessible.Rather than defaulting to silence when faced with paywalled text, ICSV cite the same source.By computing a field-normalized consensus among these downstream citers, BIBAGENT reconstructs the content of hidden sources through collective community intelligence. This shift-from direct document inspection to a multi-perspective consensus model-allows for a robust chain of integrity even when the primary record is unavailable.

Wefurther introduce twofoundational contributions for rigorous evaluation within and beyond the project. First, we formalize a Unified Taxonomy of Miscitation,categorizing errors into five distinct classes ranging from Content Misrepresentation toScope Extrapolation.Second,werelease MIsCITEBENCH,alarge-scale,cross-disciplinarybenchmark of6,350expert-validated samples spanning254fields, constructed via a"knowledge-blank"protocol to prevent LLM contamination. Together, these resources provide the first robust,generalizable testbed for automated citation verification.

In summary, our core contributions are:

- ·BIBAGENT, the first end-to-end agentic framework capableofhandlingmiscitationsinvolvingbothaccessible and inaccessible cited sources,offering a robust solutiontothepaywall problemvia acommunityconsensusmechanism.
- ·Adaptive verification: a multi-stage "zoom-in"logic balancing efficiency and precision, with explicit reasoning trails.
- ·Evaluation infrastructure:a comprehensive 5categoryMiscitationTaxonomy and M1sCITEBENCH, the largest cross-disciplinary benchmark to date, enabling scalable and reproducible assessment of citation integrity.

## 2. Taxonomy and MIsCITEBENCHConstruction

Automatedmiscitation detectionrequires aprecise characterization of how citationscanfail.Priorworklargely limitedtoanecdotalcasestudiesorcoarsebinarylabels (valid vs.invalid) (Pride &amp; Knoth, 2017; 2020), and domainspecific typologies (e.g., in clinical medicine or psychology) built around loosely defined sentiment categories (Wadden et al.,2020;2022;Wadden&amp;Lo,2021;Sarol et al.,2024). These schemes are challenging to generalize across fields heterogeneous corpora.To our knowledge, there is still no unified taxonomy that (i) is mutually exclusive and collectivelyexhaustiveattheerror-codelevelformulti-field scientific corpora and (ii) can be applied reproducibly across disciplines.

We address this gap by introducing (i) a five-category taxonomy of miscitation errors governed by simple operational "litmus tests,"and (ii) MIsCITEBENCH,a contaminationcontrolled benchmark that instantiates this taxonomy at scale across all 254 Clarivate Journal Citation Reports (JCR) (Clarivate, 2025) subject categories and 21 broader



--- Page Break ---



disciplines. Conceptually, our taxonomy decomposes miscitationalongfiveorthogonaldimensions-statusofthe source,factualcontent，scopeofapplication,evidence strength,and attributionlink—whichjointlycover allfailure modes observed in our corpus.MIsCITEBENCH realizes thistaxonomyasaknowledge-blank,adversarialstresstest for LLM-based citation reasoning,rather than merely a labeled dataset.Table1 summarizes howlegacylabels from prior miscitation studies are absorbed into these categories.

Table 1. Mapping from legacy miscitation labels to our unified 5-category taxonomy.

| New Category                      | Core Litmus Question                                                                                                        | Absorbed Legacy Subtypes                                                                                 |
|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| Citation Validity Error           | Isthesourceitself disqualifiedfrom serving asscientific evidence?                                                           | Obsolete or Retracted Citation; Secondary-Source Misuse                                                  |
| ContentMis- representation Error  | Does the source,when readin context, actuallysaywhatthe citingtext claimsit says?                                           | Irrelevant Citation; Contradictory Citation; Selective Quotation; Omitted Qualifiers; Conflated Findings |
| Scope Extrapolation Error         | Isanotherwisevalid conclusion being appliedoutsidethe population,setting,orData-ScopeMisuse taskforwhichit was established? | Overgeneralization; Methodological Misapplication;                                                       |
| Evidence Characteriza- tion Error | Is the type/strength ofCorrelation-as- causal,definitive) actuallysupportedby thestudydesign and statistics?                | evidence claimed(e.g.,Causation; Statistical orMetricalDistortion                                        |
| Attribution& Traceability Error   | CanareaderreliablyGhost Citation; locateandcorrectly attributethesource usingtheprovided citationmetadata?                  | AuthorMisattribution                                                                                     |

## 2.1.A Unified 5-Category Taxonomy of Miscitation

Starting from a survey of existing typologies and a manual auditofhundredsofreal-worldmiscitationssampledacross all 21 high-level disciplines,we consolidate previously scattered subtypesintofive conceptuallydistinct categories. Each category is defined by a diagnostic litmus question that makes annotation operational and reproducible.

- 1.Citation Validity Error (Status of the Source). Thecitedworkitselflacksqualification asscientific evidence——for example,it has been retracted,superseded, or is a secondary source (e.g., a review or metaanalysis)being cited asif it were primary experimental
- evidence.Theerror concerns thestatus ofthesource, not its content. Litmus question:"Is the source itself disqualified from serving as scientific evidence?" This category subsumes Obsolete or Retracted Citation andSecondary-SourceMisuse.
- 2.Content Misrepresentation Error (Factual Content). Thecitingtextsubstantivelydistorts,fabricates,orreverses the findings, arguments, or conclusions of the source. Examples include citing a topically unrelated paper as evidence (Irrelevant Citation),citing a refutation as support (Contradictory Citation),or selectively quoting while omitting key qualifiers so that the meaning changes(SelectiveQuotation,OmittedQualifiers, Conflated Findings).Litmus question:"IfI read the sourceincontext,doesitactuallysaywhattheciting sentenceclaimsitsays?"
- 3.ScopeExtrapolationError (Scope of Application). The source is correctly understood,but its conclusion is applied beyond the populations, settings, tasks, or methods for which it was established.Typical cases includeOvergeneralizationfromnarrowsamplesto broadpopulations,MethodologicalMisapplication outside validated constraints,and Data-Scope Misuse that promotes a subset analysisto a claim about thefull dataset.Litmus question:"Is an otherwisevalid conclusionbeingappliedoutsidethepopulation,setting, or task for which it was established?
- 4.Evidence CharacterizationError (Evidence Strength).The citing text mischaracterizes thelogical type,strength,or certainty of the evidence in the source. This includes treating correlational findings as causal(Correlation-as-Causation)orexaggerating statisticalevidence(Statistical orMetricalDistortion), such as describing marginal effects as "conclusive andstrengthofevidenceclaimedinthecitingtext actuallysupportedbythesource'sstudydesignand statistics?"
- 5.Attribution&amp;TraceabilityError(Attribution Link).Errorsin citationmetadatabreak thelink between claim and source.Examples include nonexistentorunresolvablereferences(GhostCitation) and assigning a result to the wrong author or paper (AuthorMisattribution).Theerrorconcernsthecitation as ascholarlysignpost,not theunderlyingevidence. Litmus question: "Could a reader, using only this citationmetadata,reliablylocatethecorrectsource andauthoroftheclaimedidea?"

Thesefivecategoriesweresufficienttolabelall6,350miscitationinstancesinMIsCITEBENCH(Section2.2)without an"other"bucket. Annotators assign exactly one primary



--- Page Break ---



category per instance, guided by the litmus questions above. When multiple error types co-occur, we enforce a logical DependencyPrecedenceRulethatmirrorstheverification process: checking a citation aborts at the first point of failure. Theprecedence orderis:

Attribution&amp;Traceability→CitationValidity→Content Misrepresentation→ScopeExtrapolation→Evidence Characterization.

For example,if the citation metadata is unusable(Attribution),onecannot assessretractionstatus(Validity)orcontent fidelity (Content), so Attribution becomes the primary label.

In an expert annotation study (Appendix B) where annotayielded Cohen's k in the"substantial"range, and fallback options wererarelyused.Together with the absence of an "other"bucket in M1sCITEBENCH, this provides empirical evidence that the taxonomyisboth completefor our corpus and operationally consistent.In theremainder of this work, itservesas(i)thelabelspaceforMIsCITEBENCHand (ii) theerror codespacepredicted by ourBIBAGENT.

## 2.2.MIsCITEBENCH:AContamination-Controlled EvaluationFramework

Existing miscitation datasets are typically narrow in domain,dominated by trivial errors,and vulnerable to data parametric memorization rather than by reasoning over thedocumentspresentedatevaluationtime.Weintroduce MIsCITEBENCH,a large-scalebenchmark of6,350expertvalidated miscitation instances that (i) spans all 254 ClarivateJCR subject categories and 21 high-level disciplines (including Agricultural Sciences, Clinical Medicine, Computer Science, Social Sciences, and Visual &amp; Performing Arts), and (i) is aligned with the five-category taxonomy above. MIsCITEBENCH is constructed under two design principles:aKnowledge-BlankCleanroomProtocol that filtersoutcontaminatedsources,andaDual-TierAdversarial Generation pipeline that yields both surface-level and deep-semanticmiscitations.

## SourceSelection andKnowledge-BlankCleanroomPro-

tocol.For each of the 254JCR subject categories,we identify the 2024Journal Impact Factor(JIF)leader and then select,within that journal, the most-cited article published in 2024-2025; a detailed rationale forusing most-cited articles as benchmark sources is provided in Appendix A.2. Wemanuallyretrievethefulltextofeachcandidatesource paper. To decouple reasoning from memorization, we probe a panel of frontier LLMs/LRMs (e.g., gpt-4o (Hurst et al.,2024),04-mini-2025-04-06 (OpenAI,2025b), claude-sonnet-4 (Anthropic,2025); details in Appendix A.2) with 10 forensic questions per paper. Each ques- tionisdesignedsothat answeringitcorrectlyrequires access to the main body or appendices (e.g., specific numerical results, methodological caveats, cross-section comparisons) and cannot be solved from title, abstract, or bibliographic metadata alone.

A candidate sourceis admitted onlyif everymodelin the panel answers zero of the N probes correctly. If any model answers at least one probe correctly,we discard that paper and test the next most-cited article in the same journal and time window,repeating until we obtain a source that satisfies this knowledge-blank criterion. This protocol substantially reduces the chance that models can rely on parametric knowledge of the paper's content; at evaluation time they mustinsteadreasonoverthecontextualdocumentsweprovide. The procedure is model-agnostic and can be re-applied as stronger LLMs emerge.

Dual-TierAdversarialGenerationandExpertValidation. For each retained source paper, we use a state-of-the-art Large Reasoning Model (LRM; gemini-2.5-pro (Comanici et al.,2025;Google, 2025)）togenerate 25adversarialmiscitations grounded in the taxonomy: 5 per category. Prompts expose the five categorydefinitions and litmus questions sothat each synthesized miscitation corresponds to a well-defined error code rather than an ad hoc negative example. Within each category, we instantiate a two-tier difficulty structure:

- ·Surface-Level Miscitations (3 per category): errors falsifiable by inspecting a single sentence or local paragraph, such as obviously irrelevant citations or explicit statistical distortion.
- ·Deep-Semantic Miscitations (2 per category): expertlevel traps that mimic plausible scientific discourse but subtly violate global document logic, such as extrapolating conclusions to incompatible populations or require integrating results, limitations, and discussion.

Each instance packages (i) the erroneous citing sentence, (ii) the gold supporting span from the source, (i) a naturallanguage explanation of the miscitation and its taxonomy label, and (iv) a corrected version of the citation.We then perform carefully and thoroughly cross-validationusing an independent LRM (gpt-5.1-thinking (OpenAI,2025a)） and human experts in the corresponding sub-discipline(verification criteria and prompts in Appendix A.3). Instances for which the two validators disagree are revised or discarded.

This pipeline yields a contamination-controlled benchmark with a consistent structure of 254 source papers × 5 taxonomy categories x 5 instances per category,for a total of 6,350 miscitation cases.MIsCITEBENCH thus spans a wide range of di



--- Page Break ---



MIsCITEBENCH thusprovides a spectrum of difficulty that includesbothstraightforwardsanity-checkfailures andsubtle expert-level miscitations, and-as shown in Section 4serves as a stress testfor miscitation detectors under distribution shift, especially for LLM agents that must reason

## 3. BIBAGENT: The Bibliographic Miscitation DetectionAgent

We propose BIBAGENT,an end-to-end agentic frameworkdesignedtorestoretraceable,citation-levelaccountability to scientific discourse. Rather than processing pairs of papers monolithically in a single long LLM call, BIBAGENT orchestrates a modular pipeline that (i) handlesboth accessibleandinaccessible(paywalled)sources and (i) outputs miscitation judgements aligned with our five-category taxonomy, together with explicit citing contexts, evidence spans, and confidence scores. The system comprises four modules:(1)Document Parser&amp; Citation Mapper(DPCM),(2)CitedSourceAccessibilityClassifier (CSAC),(3)AccessibleCitedSourceVerifier(ACSV),and (4) Inaccessible Cited Source Verifier (ICSV). Together, these modules take a single citing paper and produce both fine-grained,citation-leveljudgements andpaper-level summaries of its overral citation integrity (Section 4).

## 3.1. Citation Parsing and Accessibility Routing

Thepipelinebeginswith theDocumentParser and Citation Mapper (DPCM), which accepts LTeX source, XML/HTML,and PDF inputs and explicitly prioritizes citation fidelity.Crucially,DPCM normalizes everyinput-regardless ofitsoriginalformat-intoastructuredMarkdownintermediate representation that preserves the document's discourse skeleton: hierarchical headings, paragraph boundaries, inline math and displayed equations, figure/table captions, footnotes, and in-text citation anchors. This unified representation ensures that downstream verification operates on a consistent, traceable substrate rather than brittle formatspecific text dumps.

Formarkupformats,DPCMremovesnon-semanticmacros andformattingcommandswhilepreservingstructuralsignals(e.g.,sectiontitlesand theirlevels),mathematicalexpressions,and citation commands(e.g,\cite,ref). It thenrendersthecleanedcontent intohierarchical Markdown with explicit heading levels and stable citation anchors, so that the logical argument flow and citation contexts remain intact acrosspublishersand authoringstyles.

For PDFs, DPCM uses a hybrid visual-linguistic parsing strategy that directly transcribes pages into the same structured Markdownrepresentation.Eachpage issegmented intospatially coherentblocks via a sliding window,raster- ized, and passed to a layout-aware multimodal model (i.e., tracted text. Guided by visual cues such as whitespace,font weight, column boundaries, and figure/caption geometry, themodel performs layout-groundedserialization:it reconstructs the reading order of multi-column text and faithfully places floating figures, captions,sidebars,and footnotes into the appropriate Markdownlocations,preserving both heading hierarchy and citation anchors.The exact multimodal prompting template and the image-to-Markdown transcription logic (including block serialization rules and failure-handling heuristics) are provided in Appendix C.

Tominimizeinformationloss,anExtractionVerifieraudits thetranscribedMarkdownforstructural andbibliographic continuity markers—monotonic section-heading progression,equationnumbering,andcitationindexsequences (e.g., [12]→[13]). When it detects a discontinuity (e.g., a missing citation index, a broken equation sequence,or an implausible heading jump), it triggers localized re-parsing of the corresponding visual block at an adjusted resolution and re-integrates the repaired span back into the Markdown representation. This closed-loop verification mitigates OCR dropouts,misrecognized symbols, and fragmented sentences before downstream citation reasoning,ensuring thateverylaterdecisionremainstraceabletoafaithful,structurally aligned document rendering.

TheCitationMapper thenidentifiesin-text citation spans at the sentence level and links them to bibliographic entries, supporting more than 15 citation styles (e.g.,APA, IEEE), grouped citations (e.g.,"[3,5,9]"), cross-referenced footnotes, and idiosyncratic delimiters. The result is a structured mapping from localized citing contexts to their referenced sources,with style-normalized metadatafor each link. All downstream judgements consume this mapping, which keepseverydecisiontraceabletoconcretecitationcontexts and bibliography entries. By committing all inputs to a single hierarchical Markdown representation with stable citation anchors, DPCM makes every downstream judgement auditable: each verdict can be traced back to the exact citing context and the exact source span in a format-invariant way.

TheCitedSourceAccessibilityClassifier(CSAC)then routes each cited source.For every bibliographic entry, CSAC first attempts to resolve a DOI; if none is available,it constructs a metadata query from title, authors,and year. It queries official publisher or venue APIs to retrieve full text wherepossible.If thisfails,it performs asecondarysearch over curated open-access repositories (e.g., arXiv, PubMed Central, SciELO, domain-specific preprint or institutional repositories). For each candidate match, CSAC compares title, author list, abstract, and (when available) reference list, accepting only open-access surrogates that are substantively identicaltothepublisher'sversion.



--- Page Break ---



CSAC also supports attribution checking.If the primary search yields no valid metadata record (e.g., invalid similarity matches, the reference is flagged as a Ghost Citation(Attribution&amp;TraceabilityError)anddirectlyfinalized, preventing hallucinated rationales for non-existent papers. ReferenceswithverifiedfulltextareroutedtotheAccessiblestream.Referenceswithvalid metadatabut nofull-text access are assigned a rich metadata snapshot (title, authors, abstract,venue,partial references)and routed to the Inaccessible stream, which is later consumed byICsV.

## 3.2.ACSV:AdaptiveMulti-StageVerification

For accessible sources, the main challenge is to balance cost and reasoning depth. Naively feeding two full papers into a long-context LLM/LRM is expensive and prone to "lost-in-the-middle"errors.We instead use an Adaptive Multi-StageVerificationarchitecturethatactsasacomputationalfunnel:low-cost denseretrieval andNLI resolve easy cases, while only genuinely ambiguous citations are designunderpins theMIsCITEBENCH Open-regimegains reported in Section 4: across backbones, it improves miscitation detection accuracy over Full-Text baselines while reducing token usage by up to 79.4%.

Phases I-Il:Coarse Retrieval and Focused Reranking. Let Seite denote the citing sentence and Dcited thesource document.We segment Dcitedintopara：A Bi-Encoder(instantiated as all-MiniLM-L6-v2 (Reimers &amp; Gurevych,2019)) maps Scite and each p into a shared vector space and retrieves top-K paragraphs via cosine similarity:

$$S o r e _ { r e t r i v e l } ( S _ { c i t e , \, p _ { i } } ) = \cos ( v _ { S _ { c i t e } , \, v _ { p _ { i } } } ) = \frac { v _ { S _ { c i t e } \cdot \, v _ { p _ { i } } } } { \| v _ { S _ { c i t e } } \| \, \| v _ { p _ { i } } \| } . \, ( 1 ) \quad _ { s h e l f } ^ { \, \ v 3 - \, \text {lar} _ { 5 } } .$$

A

$$\begin{matrix} \text {Cross-Encoder} & & & ( e . g , , & & \text {Ph} ) \\ & & & & & ( e . g , , & & \text {Ph} ) \end{matrix}$$

ms-marco-BERT-base-v2 (Reimers &amp; Gurevych, 2019)) then re-ranks the top-K candidates and selects the top-N segments Pfocus. In our experiments we set K = 10 and N =3,which empirically recovers sufficient context for complex arguments whilekeeping the evidence pool withintheeffectivecontextwindowofdownstreammodels.

To preserve inter-sentence dependencies while avoiding paragraph-level noise,we apply a slidingwindow over each paragraph in Pfocus, generating cited-side context windows Wcited of Wsize consecutive sentences with stride 1 (default Wsize = 3).

Phase MI: NLI-Based Logic Filtering with Dynamic Expansion.At this stage, the goal is to decide,as cheaply as possible,whether the retrieved evidence already settles the citation. We therefore apply a Natural Language Inference

(NLI) model to each evidence window w E Wcited, treating thewindow as thepremiseand theciting sentence as the hypothesis. For every w, the model outputs a three-way distributionoverEntailment(E),Contradiction(C),and Neutral (N):

$$\begin{array} { c c } \text {apels.} & P ( E , N , C \, | \, w , S _ { c i t e } ) = N L I ( \text {premise} = w , \text { hypothesis} = S _ { c i t e } ) . \\ \text {cceSSI-} & \quad \text {cite} \end{array} \quad ( 2 )$$

We thenimplementanEarlyExitrulethatshort-circuits easy cases. Let

$$M _ { E } = \max _ { w \in \mathcal { W } _ { c i t e d } } P ( E \, | \, w , S _ { c i t e } ) , \\$$

$$M _ { C } = \max _ { w \in \mathcal { W } _ { c i t e d } } P ( C \, | \, w , S _ { c i t e } ) ,$$

denote the strongest entailment and contradiction signals across all windows. Whenever either signal crosses a highconfidence threshold Thigh, we immediately commit to a decision:

$$\text {Decision} = \begin{cases} \text {Correct,} & M _ { E } > \tau _ { \text {high} } , \\ \text {Miscitation, } & M _ { C } > \tau _ { \text {high} } . \end{cases} \quad ( 5 )$$

When neither entailment nor contradiction exceeds Thigh,or when both do so with conflictinglabels,the case is treated as ambiguous. To address this,we dynamically expand the hypothesis by incorporating its immediate neighbors in the citing document:

$$S _ { \text {expanded} } = \text {concat} ( S _ { \text {prev} } , S _ { \text {cite} } , S _ { \text {next} } ) ,$$

and re-run NLI with Sexpanded as the hypothesis while keeping Wcited as the set of premises. In all experiments, we instantiatetheNLI modelwithapubliclyavailableDeBERTav3-large checkpoint that is pre-trained for NLI, use it off-theshelf without any additional fine-tuning, and fix Thigh = 0.9.

Phase IV: LRM Deep Reasoning via Self-Consistency. Cases that remain ambiguous enter themost expensive phase.We construct a Chain-of-Thought prompt containing Sexpanded and Pfocus and query a Large Reasoning Model (LRM, e.g., gemini-2 .5-pro) to perform semantic arbitration (supported vs. miscitation vs. undecidable). To mitigate stochastic artifacts,weenforceSelf-Consistency: we query the LRM M times with different sampling seeds at temperature T (default M = 5, T = 0.7), obtaining verdicts {V1,... , Vm }, and adopt the majority class as the final label. We define a confidence score

$$C o n f i d e c e _ { L R M } = \frac { C o n t ( M a j o r i t y \ V e r d i c t ) } { M } . \quad ( 7 )$$

If ConfidenceLRM &lt; 0.6, ACSV outputs an "Undecidable— Requires manual review" label instead of forcing a brittle decision.



--- Page Break ---



## PaywalledSourceBisVerifiedviaCommunityConsensus-NotByHallucinatingB.

aggregate downstreamopen-accesswitnesses→clusterspans→distillevidencestatements→influence-weightedvoting→reliableconsensusorabstain

* Reliable when ≥ 6independent witnesses per aspect; otherwise abstain.

Figure 1.Overview of theINACCESSIBLE CITEDSoURCEVERIFIER(ICSV)andits Evidence Committee mechanism.Given a citing context about a paywalled source B,ICsV (1)extracts an atomic claim that captures exactly what the citingpaper attributes toB; (2) retrieves open-access downstream citers of B and clusters their local citation contexts into aspect-specific groups; (3) distills each group intoa canonicalevidencestatement,weightingit by afield-normalizedinfluencescore thatcombinesvenueandpaper-levelimpact;and (4)aggregates the resulting entailment/contradiction/neutral votes into a reliability-aware consensus verdict,explicitly abstaining when community evidence is toosparse orinternallyinconsistent.This convertspaywalledmiscitation detectionfrom aninaccessible-document problemintoa traceable,community-consensus reasoning task.

<!-- image -->

## 3.3.ICSV:TheEvidenceCommitteeMechanism

TheInaccessibleCitedSourceVerifier(ICSV)handles sources B whose full text is behind a paywall or otherwiseinaccessible.Figure1summarizes theresultingEvidence Committeepipeline thatreconstructs thecommunity'sview of such sources.Since direct textualentailment against B is impossible,ICsV adopts a CommunityConsensusReconstruction approach:ittreats downstream citations as a distributed,noisy memory of B's contributions and reconstructs those contributions by aggregating and weighting statements from open-access witness papers. Individual downstream citers may miscite B, soICsVexplicitlymodelseachevidencestatementasa noisy vote and relies on field-normalized influence weights and abstention thresholds to maintain reliability.Throughout this module,all LLM calls share a single backbone (gpt-4o-2024-08-06)but are driven by task-specific prompt templates and decoding hyperparameters; we documeent these prompts, sampling configurations, and postprocessing rules in detail in Appendix D.

(1)Context-AwareCitingClaimExtraction.Givena citing sentence sA in paper A that references inaccessible sourceB,weconstructalocalcontextwindowWAbyconcatenating the preceding,current, and succeeding sentences (default Lwin = 3). An LLM is prompted to extract from WA a single, self-contained atomic claim cA that captures exactly what A attributes to B,resolving pronouns and removing side information. The prompt admits a special IN-SUFFICIENT\_CONTEXT token;if returned,we expand WA (e.g., to Lwin = 5) and retry until we obtain a stable CA or mark the case underspecified.

(2）CommitteeFormation and EvidenceDistillation. We retrieve a set of open-access downstream citers Copen = {p1,...,Pm} that reference B. For each mention of B, we extract a context-rich span comprising theciting sentence and its neighbors, forming a set S = {s1,... }. We embed all spans and cluster them; an LLM is used to refine clusters so that each G;represents a coherent aspect of B (e.g., algorithmic contribution vs. dataset construction). For each cluster G, an LLM distills its spans into a canonical Evidence Statement ej, yielding an evidence set E = {e1,...,ek} that summarizes the community's distributedview ofB alongmultiple semantic axes.

(3) Field-Normalized Influence Modeling. Citation and venue statistics vary drastically acrossfields and years.We therefore define a Field-Normalized InfluenceScore Z(p) for each committee member p E Copen. Let IF(p) be the impactfactorof p'svenue andCite(p)itsrawcitationcount. We normalize both against the appropriate JCR Subject



--- Page Break ---



Category and publication year:

$$J _ { n o r m } ( p ) = R a n k _ { \% } \left ( \text {IF} ( p ) \, | \, \text {Field} ( p ) \right ) , \quad ( 8 ) \quad \text {Beyon}$$

$$C _ { n o r m } ( p ) = R a n k _ { \% } ( C i t e ( p ) \, | \, \text {Field} ( p ) , Y e a r ( p ) ) , \quad ( 9 ) \quad \text {from to}$$

and aggregate them as

$$\mathcal { I } ( p ) = w _ { c } \cdot C _ { n o r m } ( p ) + w _ { j } \cdot J _ { n o r m } ( p ) , \quad ( 1 0 ) \quad _ { c l e t r }$$

where we set wc = 0.6 and w; = 0.4. Crucially, we assign than venue prestige (w§). This design choice explicitly mitigates the "halo effect" of top-tier journals, ensuring that highly infuential papers published in niche or lower-impact venues are correctly recognized as credible evidencesourcesbythecommittee.

The credibilityof an evidence statement e;is thenormalized sum of influences from all papers contributing spans to cluster Gj. Let SourcePaper(s) denote the paper from which span swas extracted.We define

$$\text {Support} ( e _ { j } ) = \sum _ { s \in G _ { j } } \mathcal { I } ( \text {SourcePaper} ( s ) ) , \quad ( 1 1 ) \quad \text {exact} \quad \begin{array} { c c } \text {zero} - \text {supset} \\ \text {two} \end{array} \quad \text {and} \quad \begin{array} { c c } \text {zero} - \text {supset} \\ \text {two} \end{array}$$

$$\gamma _ { j } = \frac { \text {Support} ( e _ { j } ) } { \sum _ { i = 1 } ^ { k } \text {Support} ( e _ { i } ) } , \quad ( 1 2 ) \quad \text {In} \\$$

where j E [O, 1] is the credibility weight of ej.

(4）Reliability-AwareWeightedConsensusVerdict. For each ej, an LLM classifies the relation Rj E {Entailment, Contradiction, Neutral} between e and CA, which we map to a scalar vote v; E {+1, 0, -1}. We then compute a credibility-weighted consensus score

$$\mathcal { V } _ { \text {final} } = \sum _ { j = 1 } ^ { k } v _ { j } \cdot \gamma _ { j } , \quad \quad \quad ( 1 3 )$$

with Vinal E [—1,1].A citation is labeled Supported if Vfinal &gt; Tsupport, Miscitation if Vfinal &lt; Tmiscite, and Undecidable otherwise, with |Vinal| serving as a confidence score. In all experiments we set Tsupport = 0.3 and Tmiscite = -0.3.

Communityevidenceissparsewhenfewdownstreamciters exist.Our pilot studies (Section 4）show a sharp increase in verdict stability once an aspect is supported by at least Kmin = 6 independent witnesses. Guided by this, ICSVenforces a Reliability-AwareAbstentionprotocol:if [Copenl &lt; Kmin or if Vfinal E [Tmiscite, Tsupport], ICSV abstains instead of forcing a brittle verdict. This design prioritizes precision over recall in high-stakes settings, avoiding false accusations when community evidence is weak while exploiting the research community's distributed memory when it is sufficiently rich.

## 3.4. Taxonomy-Aligned Labeling

Beyond deciding whether a citation is factually valid, BIBAGENT aims to assign a fine-grained miscitation type from the five-category taxonomy. For every citation flagged as a miscitation by ACSV or ICsV, we invoke a lightweight taxonomy classifier that operates over the same evidence context, augmented with CSAC-derived metadata (e.g., article type, retraction status)where available.

ToenforcetheDependencyPrecedenceRulefromSection 2.1,the classifier is prompted with a hierarchical decisiontree:itmustfirstcheckforAttribution&amp;Traceability failures using CSAC's resolution results; if none apply, it considers Citation Validity (e.g., retraction, secondarysourcemisuse),then Content Misrepresentation,and only thenScopeExtrapolationandEvidenceCharacterization. The input bundle comprises (i) the citing context Sexpanded, (ii) key evidence windows from Wcited (for ACSV) or distilled evidence statements {e§} (for ICsV), and (ii) the five taxonomy definitions with their litmus questions. A compact LLM (i.e., 9pt-4o-2024-08-06) is used in a zero-shot, small-ensemble self-consistency setting to choose exactly onecategory and provideashortrationale;wetake the majority vote across runs.

In summary,for each citation in the input paper, BIBAGENT outputs (i) a validity judgement (Supported, Miscitation, or Undecidable), (ii) a single taxonomy-aligned error code for miscitations,(ii) the citing context with key evidence spans (or distilled evidence statements for inaccessiblesources),and(iv)ascalar confidencescore. These structured outputs underpin the paper-level citation integrity summaries reported in Section 4, and support highrecall miscitation detection with interpretable,taxonomygrounded explanations at practical computational cost.

## 4. Experiments and Results

## 4.1.EvaluationProtocol and Deployment Regimes

WeevaluateBIBAGENTonMisciteBenchundertwo regimesthatmirrorthetwodominantrealitiesofcitationverification: (i) the full-text regime, where verification should be grounded, efficient, and traceable, and (i) the paywall regime, where the full text of the cited source is unavailable, and verification must remain reliable without fabricating what the unseen source contains. These regimes directly probe the two central claims of this work:BIBAGENTcan (a) compress long-document verification without sacrificing diagnostic fidelity, and (b) reconstruct evidence forinaccessiblesources via community consensusrather thanbrittle retrieval or speculation.

Regime I: MisciteBench-Open (Accessible Sources).In thissetting,thefull textof thecitedsourceis available.Each



--- Page Break ---



instance provides the citing sentence (with its local citing context) and the complete cited paper, and is routed to ACSV. The system outputs (i) a validity judgment (Supported vs. Miscitation)and(i)adiagnosisthatmustbefaithfultothe gold miscitation rationale under our taxonomy.

## RegimeII:MisciteBench-Paywall (InaccessibleSources).

In this setting,the cited source text is not provided; only bibliographicmetadata and downstream open-access citers are available,and the instance is routed toICsV. This is a strictinaccessibilityconditionratherthanacontrivedablation:MisciteBenchis constructedvia aknowledge-blank paper whose content can be answered correctlyby the tested backbones through parametric memorization. As a result, withholding the source text genuinely forces models to operate under paywall constraints.

EvaluationunderPaywallConstraints.MisciteBench includesbothsurface-level anddeep-semanticmiscitations. Surface-levelcitationsrefer torelativelystraightforward factual references, such as key statistics,population characteristics,samplesizes,orotherclearlystateddescriptive elements, that can typically be verified without requiring a comprehensive reading or deep conceptual understanding of the cited article.In contrast, deep semantic miscitations involve claims that depend on a holistic interpretation of the cited work, often requiring integration across its results, assumptions, limitations, and discussion. When the full text of the cited paper is inaccessible, evaluating deep semanticmiscitationsbecomesintrinsicallyunderdetermined. Moreover, prior research on citation function has shown that manycitationsservedescriptive orperfunctoryrolesrather than deep substantive engagement (Budi &amp; Yaniasih, 2023; Kunnath et al., 2021), suggesting that surface-level verification captures a substantial and practically relevant portion of how scholarly citations are actually used.Accordingly, under the paywalled setting, we restrict evaluation to the surface-levelsubsetofMisciteBench,yielding3instances per category × 5 categories × 254 fields,for a total3,810 examples.

## 4.2.Baselines andWhyBackbone-Controlled Comparisons AreNecessary

Miscitation detectionfaces not onlymethodological heterogeneitybutalsoapersistentreproducibilityandapplicability gap in existing benchmarks and baselines.Despite substantialwork oncitationsentiment andscientificclaim verification (Wadden et al.,2022; 2020; Press et al.,2024; systems rely on small, domain-limited collections, shortcontext evaluation,or incompletely documented pipelines, making fair, end-to-end comparison difficult. In practice, data are often inaccessible, paywalled, or structurally in- complete forlong-context verification; links to evaluation code or checkpoints are missing; and many systems lack support for long-document evidence and remain tailored to abstract-level or snippet-level entailment, misaligned with MisciteBench's long-document, diagnosis-critical setting. Under these conditions, reporting superficial cross-paper numbers risks creating only theillusion of comparability while failing the standards of reproducible science.

Wetherefore adopt architecture-agnostic,backbonecontrolledbaselinesthatisolatetheincrementalcontribution of BIBAGENT's agentic decomposition,while remaining fully reproducible and strictly matched in model capacity:

- Full-Text (Open regime): concatenate the citing context and the entire cited paper into a singleprompt and askthesamebackbone todecideSupportedvs. Miscitationandexplainwhy.
- ·Search(Paywallregime):allowthebackbonetocall web search tools to locate potential open-access surrogates and thenverify against retrieved snippets or documents.This baseline is intentionally generous:it
- ·BIBAGENT:the same backbone embedded inside our pipeline (ACSV for Open; ICSV for Paywall). Crucially,ICsV runs ofline without external search to measurewhetherBIBAGENTcanpreservecitation integrity when retrieval is fundamentally unreliable or incomplete.

This backbone-controlled design answers the core scientific question of this paper without confounding: given thesameLLM/LRM,doestheagenticverificationstructure(retrieval/NLIfunnel;committeeconsensus)convert long-contextandpaywallverificationfromabrittleprompt intoareliableprocedure?Inotherwords,wetreatthelack of reliablebaselines not as aninconveniencebut as an empiricalfact about thefield'scurrenttooling: a community reproducibility gap that motivates, rather than undermines, backbone-matchedevaluation.

## 4.3. Metrics

Primarymetric:Acc-pass@3.WemeasurebothcorrectnessanddiagnosticfaithfulnessusingAcc-pass@3.For each instance,a method is sampled three times with differentdecodingseeds.Apredictioniscountedascorrectifany of the three outputs simultaneously:

- ·predicts the correct validitylabel(Supportedvs.Miscitation),and
- provides anexplanation that issemanticallyequivalent



--- Page Break ---



to the gold miscitation rationale (i.e., it identifies the failure mechanism, not merely the label).

Semantic equivalence is judged by an independent LLM grader(gpt-4o-2024-08-06) under a rubric that penalizes partial matches, generic paraphrases, and post-hoc hallucinations (details and robustness checks in Appendix E). Thismetricreflectstheeditorialrequirementthatadetector must not only flag a miscitation but also justify it with traceable reasoning.

Efficiency metric: Token Economy. For MisciteBenchOpen,we additionallyreport TokenEconomytherelative reduction in total tokens processed per instance (inputs + outputs)compared tothe correspondingFull-Textbaseline using the samebackbone,computed oninstances whereboth methods return a verdict.Token accounting and decoding settings are described inAppendixE.

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

Table2.MisciteBench-Open:miscitationdetectionanddiagnosis when full texts of cited sources are accessible.Token Econ reports thepercentageoftokenssavedbyBIBAGENTrelativetothe correspondingFull-Textbaseline.

| Model                            | Org.   |                    | Scenario|Acc-pass@3↑|TokenEcon↑   |      |
|----------------------------------|--------|--------------------|-----------------------------------|------|
| gpt-5-2025-08-07                 | S      | BIBAGENT Full-Text | 92.1 98.8                         | 65.3 |
| 04-mini-2025-04-16               | S      | BIBAGENT Full-Text | 88.4 96.4                         | 79.4 |
| gpt-4o-2024-08-06                | S      | BIBAGENT Full-Text | 84.6 94.8                         | 60.2 |
| gpt-oss-120b                     | S      | BIBAGENT Full-Text | 82.9 92.7                         | 59.3 |
| gpt-oss-20b                      | S      | BIBAGENT Full-Text | 87.6 72.4                         | 70   |
| claude-sonnet-4-20250514         | 米     | BIBAGENT Full-Text | 91.3 97.8                         | 74.7 |
| claude-opus-4-20250514           | 米     | BIBAGENT Full-Text | 100.0 94.3                        | 44.6 |
| gemini-2.5-pro                   |        | BIBAGENT Full-Text | 95.8 97.9                         | 74.8 |
| gemini-3-flash                   |        | BIBAGENT Full-Text | 93.1 96.4                         | 66.2 |
| gemini-3-pro                     |        | BIBAGENT Full-Text | 100.0 96.8                        | 64.7 |
| Nemotron 3 Nano (30B A3B)        | ?      | BIBAGENT Full-Text | 88.4 73.0                         | 72.1 |
| Llama-3.3 Nemotron Super 49B v1  | ?      | BIBAGENT Full-Text | 80.8 89.9                         | 66.4 |
| Qwen3-235B-A22B-Thinking-2507    |        | BIBAGENT Full-Text | 86.4 95.5                         | 61.8 |
| Qwen3 VL 32B Thinking            |        | Full-Text BIBAGENT | 79.3 92.4                         | 66.6 |
| Qwen3 VL 8B Thinking             |        | BIBAGENT Full-Text | 54.8 80.2                         | 76.5 |
| Ministral 3 (14B Reasoning 2512) | M      | BIBAGENT Full-Text | 56.2 82.1                         | 74.5 |
| Magistral Medium                 | M      | BIBAGENT Full-Text | 87.0 66.4                         | 68.3 |
| Deepseek-V3.2 (Thinking)         | R      | BIBAGENT Full-Text | 88.0 98.6                         | 62.4 |
| DeepSeek-R1-0528                 |        | BIBAGENT Full-Text | 92.4 97.2                         | 62.1 |
| Deepseek R1 Distill Qwen 32B     |        | BIBAGENT Full-Text | 92.0 76.6                         | 68.7 |
| Deepseek R1 Distill Qwen 14B     |        | BIBAGENT Full-Text | 68.4 88.1                         | 72.9 |
| Llama 3.1 405B Instruct          | 8      | BIBAGENT Full-Text | 74.5 91.0                         | 60.2 |
| Llama 3.3 70B Instruct           | 8      | BIBAGENT Full-Text | 84.6 70.3                         | 63.1 |

## 4.4.Results on MisciteBench-Open (Accessible Sources)

For accessible references,we compare BIBAGENT to FullText baselines.Full-Text is the most common"obvious" strategy in practice, but it conflates two failure modes that matter for citation integrity: (i) long-context brittleness (modelsmissordilutethedecisiveevidenceinthemiddle of a full paper),and (i) explanation drift (models generate fluent rationales that are weakly grounded in the cited text). ACSV explicitly targets both by enforcing a"zoom-in" verificationfunnel:retrieve a small,high-recallevidencepool; apply calibrated NLI with dynamic citing-context expansion; and escalate toLRM arbitration onlywhen ambiguity persists.

Table 2 shows thatACSVimprovesboth effectiveness and efficiency across allbackbones.BIBAGENTyieldsconsistentgainsinAcc-pass@3(from+5.7up to+19.8absolute points), with the largest gains appearing precisely where Full-Text prompting is most fragile under long context (e.g., gpt -4o). At the same time, ACSV reduces token usage by 44.6-79.4%, confirming that the"adaptive zoom-in"architecture resolves most instances before expensive arbitration, withoutsacrificingdiagnosticfidelity.

Failure patterns (what Full-Text gets wrong).Qualitatively,thedominantFull-Textfailures arenotrandomnoise but systematic:errors concentrate on cases where the decisive evidence is (i) expressed across multiple neighboring sentences requiring local coherence, (ii) embedded in longer chains of scientific qualification (e.g., limitations or conditional claims), or (ii) easy to paraphrase fuently yet hard to ground precisely. In these regimes, monolithic prompting oftenproducesconfidentbutweaklysupportedexplanations, whileACsV'sevidencefunnelforcesthedecisiontobeanchored to a small, explicitly retrieved Pfocus and its derived windows,reducingbothlong-context dilution and rationale drift.

## 4.5.Results onMisciteBench-Paywall (Inaccessible Sources)

Paywall verificationis the setting where the field most often fails in practice.Here, models face a fundamental dilemma: either abstain(which does not scale to editorial needs)or speculate (which destroys traceability). We compare ICSV against the Search baseline,which is intentionally optimistic: it may retrieve open surrogates that bypass paywalls, and thus is given the best possible chance to succeed.

Thegap is decisive.Evenwith web search enabled,Search baselines achieveonly22-36Acc-pass@3andfrequently fail the diagnostic requirement: they may retrieve incomplete or mismatched versions, conflate unrelated snippets, or generate plausible-sounding rationales unsupported by verifiable evidence. In contrast, ICsV improves Acc-pass@3



--- Page Break ---



<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

<!-- image -->

Table3.MisciteBench-Paywall:miscitationdetectionwhen the source text is inaccessible."Search"and"Search*"isolate two fundamentallydifferentretrievalregimes:SearchusesAPI-nativeweb searchthatisinheritedbythemodel atcall time(OpenAI:GPT5/o4-mini/GPT-4o;Anthropic:Sonnet 4/Opus4;MistralAgents: Ministral/Magistral),whereasSearch*usesourself-implemented search tool, invoked via tool calling for all other models (DeepSeek /NVIDIA/Qwen/Llama/gpt-oss).BIBAGENT uses onlyICSV's Evidence Committee without any external tools.

| Model                         | Org.|S   |                  | Scenario|Acc-pass@3↑   |
|-------------------------------|----------|------------------|------------------------|
| gpt-5-2025-08-07              | S        | Search BIBAGENT  | 36.2 80.3              |
| 04-mini-2025-04-16            | S        | BIBAGENT Search  | 29.8 66.4              |
| claude-sonnet-4-20250514      | 米       | Search BIBAGENT  | 30.2 66.8              |
| claude-opus-4-20250514        | 米       | BIBAGENT Search  | 34.4 74.2              |
| gpt-40-2024-08-06             | S        | Search BIBAGENT  | 22.1 66.5              |
| gpt-oss-120b                  | S        | BIBAGENT Search* | 16.4 69.4              |
| gpt-oss-20b                   | S        | BIBAGENT Search* | 55.7 6.6               |
| Nemotron 3 Nano (30B A3B)     | ?        | Search* BIBAGENT | 12.3 56.2              |
| Llama-3.3Nemotron Super 49Bv1 |          | Search* BIBAGENT | 11.6 59.3              |
| Qwen3-235B-A22B-Thinking-2507 |          | Search* BIBAGENT | 18.2 69.2              |
| Qwen3 VL 32B Thinking         |          | Search* BIBAGENT | 13.7 63.9              |
| Qwen3VL 8B Thinking           |          | BIBAGENT Search* | 54.2 2.1               |
| Ministral3(14BReasoning 2512) | M        | Search BIBAGENT  | 17.9 56.3              |
| Magistral Medium              | M        | BIBAGENT Search  | 28.0 62.4              |
| Deepseek-V3.2 (Thinking)      |          | Search* BIBAGENT | 14.8 76.8              |
| DeepSeek-R1-0528              |          | Search* BIBAGENT | 14.5 70.6              |
| Deepseek R1 Distill Qwen 32B  |          | Search* BIBAGENT | 9.6 62.7               |
| DeepseekR1Distill Qwen 14B    |          | Search* BIBAGENT | 8.2 59.6               |
| Llama 3.1405B Instruct        | 8        | Search* BIBAGENT | 10.3 64.3              |
| Llama 3.3 70B Instruct        | 8        | BIBAGENT Search* | 59.4 7.1               |

to 36.5-80.3 across backbones,more than doubling accuracy in every case and reaching 80.3 with gpt-5. This validatesthecorethesisofICsV:paywalledmiscitation detection is not a retrieval problembut a reliabilityproblem.TheEvidence Committeemechanismsolves thisby (i) constructing multiple independent witness views,(ii) distillingthemintocoherentevidencestatements,and(ii) aggregating them with field-normalized credibility weights andreliability-awareabstention.

Failure patterns (what Search gets wrong).The dominant Search failure mode is structural:even when retrievalsucceeds,theevidenceisoftenfragmented,version- mismatched,orcontext-stripped,makingthemodel prone to selecting the first plausible snippet and then reverseengineering an explanation. When retrieval fails (or retrieves the wrong source), the baseline degenerates into eitherabstentionorhallucinatedreconstruction.Incontrast, ICSV never claims to "read" the paywalled paper; it instead reconstructswhatthecommunitycollectivelyattributesto it,and explicitly abstains when the witness set is too small or too contradictory.

## 4.6.WhenDoes theEvidenceCommitteeBecome Reliable?

Apracticalquestionfordeploymentishowmuchcommunity evidence is needed for stable paywall verification.We perform an ablation over theclustersize|G§|for each evidence statement e; (Appendix F). The results reveal a sharp reliability transition:when an evidence statement is supportedbymorethan6independentdownstreamwitnesses (|G§|&gt; 6),B1BAGENTtypically produces high-confidence verdicts (confidence ≥ 90%),while below this threshold the framework abstains more frequently rather than forcing brittle decisions. This behavior is a deliberate integrity constraint: in high-stakes workflows, an abstention with an explicitevidenceshortageispreferableto an overconfident accusation grounded in weak or noisy community memory.

Summary.Across both regimes,BIBAGENT converts miscitation detection from a monolithic prompting heuristicintoatraceableverificationprocedure.Onaccessible sources,itsadaptive zoom-infunnelimproves diagnostic accuracy while the cutting token cost by up to 79.4%. On paywalled sources, its Evidence Committee more than doubles accuracy compared to a search-augmented baseline, despiteoperatingoffline andwithoutever claiming access to the primary record.Together, these results establish a concretepathtomaking citation chains auditable at scale in theGenAIera:efficientwhenevidenceis available,and principledwhenitisnot.

## 5. Conclusion

This work takes a step toward making scientific citation chains auditableby default.Startingfrom afieldfragmented by ad hoc error labels,short-context datasets,and paywall limitations,weintroduce three components thattogether reframemiscitationdetectionasanend-to-end,traceable reasoning problem. First, our five-category taxonomy provides an operational error code space that is both mutuallyexclusive and collectivelyexhaustive across254subdisciplines, turning vague intuitions about "bad citations" into a structured object of study.Second,MisciteBench offers a contamination-controlled,knowledge-blank benchmark of 6,350 instances that stress-tests models on both



--- Page Break ---



surface-levelandexpert-levelmiscitations,ratherthanrewarding memorization of a few canonical sources.Third, BIBAGENTitselfdemonstratesthatmiscitationcanbedetected and explainedwithhigh reliabilityby an agentic pipeline that integrates symbolic routing, efficient retrieval, calibrated NLI, and committee-based reasoning.

Empirically,BIBAGENTcloses twolongstanding deployment gaps. On accessible sources, its adaptive"zoom-in" architecture matches or surpasses full-document LLM baselines while cutting token usage by up to 79.4%, turning long-document verificationfrom a prohibitively expensive operation into a tractable one. On inaccessible sources, its EvidenceCommitteemechanismmorethandoublesmiscitaLLMs, despite operating without any direct access to the paywalled text. In an era where generative models can at scale,this combination—a principled taxonomy,a hard benchmark,and a paywall-robust agent—offers a concrete path toward self-auditing scientific workflows: draft with one model, verify with another, and keep the citation graph honest.

Looking ahead, BIBAGENTopens several avenues for buildingself-correctingresearchecosystems:tightintegration with authoring tools and journal submission pipelines; extensions tomultilingual literature and non-textual evidence (e.g., figures and code); and defenses against adversarially crafted miscitations designed to exploit model biases. But the central message is already clear. Miscitation is no longer an unavoidable side effect of scale;with the right abstractions and reasoning architecture,it becomes a measurable, diagnosable,and ultimately controllable property of scientificcommunication.

Finally, while our current focus remains on scholarly publications,theagentic architectureofBIBAGENTisfundamentally extensible.Its ability toreconstruct evidence through community consensus offers a transformative blueprint for auditing other high-stakes documents, such as grant proposals, patent applications, and policy briefs, ensuring that contextually faithful evidence.Looking ahead,we envisionBIBAGENTenabling abroader culture ofverifiable knowledge, promoting transparency, accountability, and trust acrossdomainswhereevidenceintegrityisparamount.

## References

Anthropic. Introducing claude 4, 2025. URL https: //www.anthropic.com/news/claude-4.

Athar,A.and Teufel,S.Detection of implicit citations for sentiment detection.In Van Den Bosch, A.and Shatkay,H.(eds.),Proceedings of the Workshop on De- tectingStructureinScholarlyDiscourse,pp.18-26,Jeju Island, Korea, July 2012. Association for Computational Linguistics. URL https://aclanthology.org/ W12-4303/.

Budi, I. and Yaniasih, Y. Understanding the meanings of citations using sentiment, role, and citation function classifications.Scientometrics,128(1):735-759,2023.

Chawla, D. S. The citation black market: schemes selling fake references alarm scientists.Nature,632(8027):966966,2024.

Clarivate. Journal citation reports,2025. URL https : //clarivate.com/academia-government/ scientific-and-academic-research/ research-funding-analytics/ journal-citation-reports/.

Comanici, G., Bieber, E., Schaekermann, M., Pasupat, I., Sachdeva, N., Dhillon, I., Blistein, M., Ram, O., Zhang, D.,Rosen, E.,et al.Gemini 2.5: Pushing the frontier with advanced reasoning,multimodality, long context, and nextgeneration agentic capabilities.arXivpreprint arXiv:2507.06261,2025.

Dai, C., Chen, Q., Wan, T., Liu, F., Gong, Y., and Wang, Q. Literary runaway: Increasingly more references cited per academic research article from 1980 to 2019.Plos one, 16(8):e0255849,2021.

De Lacey, G., Record, C., and Wade, J. How accurate are quotations and references in medical journals?Br Med J (ClinResEd),291(6499):884-886,1985.

Google. Gemini 2.5 pro model card, 2025. URL https://modelcards.withgoogle.com/ assets/documents/gemini-2.5-pro.pdf.

Accessed: 2026-01-11.

Greenberg,S.A.How citation distortions create unfounded authority: analysis of a citation network. Bmj, 339, 2009.

Hurst, A., Lerer, A., Goucher, A. P., Perelman, A., Ramesh, A.,Clark, A., Ostrow, A.,Welihinda, A.,Hayes, A., Radford, A., et al. Gpt-4o system card. arXiv preprint arXiv:2410.21276,2024.

Jergas, H. and Baethge, C. Quotation accuracy in medical journal articles——a systematic review and meta-analysis. PeerJ, 3:e1364,2015.

Kunnath, S. N., Herrmannova, D., Pride, D., and Knoth, P. A meta-analysis of semantic classification of citations. Quantitative science studies, 2(4):1170-1215,2021.

Liang, W., Zhang, Y., Wu, Z., Lepp, H., Ji, W., Zhao, X., Cao, H., Liu, S.,He, S., Huang, Z.,et al. Mapping the



--- Page Break ---



- increasing use of llms in scientific papers. arXiv preprint arXiv:2404.01268,2024.
- OpenAI.Gpt-5.1:A smarter, more conversational chatgpt, 2025a. URL https://openai.com/index/ gpt-5-1/.
- OpenAI. Introducing openai o3 and o4-mini, 2025b. URL https://openai.com/index/ introducing-o3-and-o4-mini/.
- Press, O.,Hochlehnert, A.,Prabhu, A.,Udandarao,V., Press, O., and Bethge, M. Citeme: Can language models accurately cite scientific claims?,2024.URL https://arxiv.0rg/abs/2407.12861.
- Pride, D. and Knoth, P. Incidental or influential?-challenges in automatically detecting citation importance using publicationfull texts.InInternational conference on theory and practice of digital Libraries,pp.572-578.Springer, 2017.
- Pride, D. and Knoth, P. An authoritative approach to citation classification.InProceedingsoftheACM/IEEEjoint conference on digital libraries in 2020,pp. 337-340, 2020.
- Qian, H., Fan, Y., Guo, J., Zhang, R., Chen, Q., Yin, D., andCheng,X.Vericite:Towardsreliablecitationsin retrieval-augmented generation via rigorous verification. InProceedingsofthe2025AnnualInternationalACM SIGIRConferenceonResearchandDevelopmentinInformationRetrievalintheAsiaPacificRegion,pp.47-54. ACM,December 2025.doi:10.1145/3767695.3769505. URL http://dx.doi.0rg/10.1145/3767695. 3769505.
- Rao,V. S.,Kumar, A.,Lakkaraju,H.,and Shah,N. B. Detecting llm-generated peer reviews. PLoS One, 20(9): e0331871,2025.
- Reimers,N.and Gurevych,I.Sentence-bert:Sentence embeddings using siamese bert-networks.In Proceedingsofthe2019ConferenceonEmpiricalMethodsin NaturalLanguageProcessing.Associationfor Computational Linguistics, 11 2019. URL http://arxiv. org/abs/1908.10084.
- Rekdal,O. B. Academic urban legends.Social Studies of Science,44(4):638-654,2014.
- Sarol, M. J., Ming, S., Radhakrishna, S., Schneider, J., and Kilicoglu, H. Assessing citation integrity in biomedical publications:corpus annotation and nlp models.Bioinformatics,40(7):btae420,2024.
- Secchi, D. A simple model of citation cartels: when selfinterest strikes science.In Conference of theEuropean Social Simulation Association, pp. 23-32. Springer, 2022.
- Simkin,M.V.and Roychowdhury,V.P.Copied citations create renowned papers? arXiv preprint cond-mat/0305150, 2003.
- Teufel, S., Siddharthan,A.,and Tidhar, D.Automatic classification of citation function. In Proceedings of the 2006 conferenceonempiricalmethodsinnatural language processing,pp.103-110, 2006.
- Wadden, D. and Lo, K. Overview and insights from the sciver shared task on scientific claim verification.arXiv preprint arXiv:2107.08188,2021.
- Wadden, D., Lin, S., Lo, K., Wang, L. L., van Zuylen, M., Cohan, A., and Hajishirzi, H. Fact or fiction: Verifying scientific claims.arXiv preprint arXiv:2004.14974,2020.
- Wadden, D., Lo, K., Wang, L. L., Cohan, A., Beltagy, I., and Hajishirzi, H.  MultiVerS: Improving scientific claim verificationwith weak supervision and fulldocument context. In Carpuat, M., de Marneffe, M.-C., and Meza Ruiz,I. V. (eds.), Findings of the Association for Computational Linguistics: NAACL 2022,pp. 61-76,Seattle,United States,July 2022.Association for Computational Linguistics. doi: 10.18653/v1/2022. findings-naacl.6. URL https: //aclanthology. org/2022.findings-naacl.6/.
- Walters, W. H. and Wilder, E. I. Fabrication and errors in the bibliographic citations generated by chatgpt. Scientific Reports,13(1):14045,2023.
- Waltman, L.A review of the literature on citation impact indicators.Journal of informetrics,10(2):365-391,2016.
- Wei, J., Huang, D., Lu, Y., Zhou, D., and Le, Q. V. Simple els,2024.URLhttps://arxiv.org/abs/2308. 03958.
- Wilhite,A. W. and Fong, E. A. Coercive citation in academic publishing.Science,335(6068):542-543,2012.



--- Page Break ---



## A.MisciteBenchConstructionDetails

## A.1.SourceSelectionRationale

Our goal in constructing M1sCITEBENCH is to obtain a contamination-controlled, cross-disciplinary benchmark that (i) represents the actual scientific articles that structure theirfields and (ii)admitsrichdownstream citation structurefor the Evidence Committee inICSV. This motivates our choice of"most-cited article in theJIF-leading journal perJCR subject category"ratherthanrandomsampling.

Concretely,for each of the 254 Clarivate JCR subject categories,we perform the following steps:

1. Journal selection. We identify the 2024 Journal Impact Factor (JIF) leader within the subject category. When multiple journals share identical JIF up to three decimal places, we break ties by (i) total citable items and then (i) alphabetical order of journal title.
2. Article-level selection. Within the JIF-leading journal, we consider all "research article"-type items published in 2024-2025.1 Among these, we select the most-cited paper according to citation counts as of 2025-11-30. Citations neighboringfields.
3. Eligibility checks.  We discard candidate sources that (a) are not primarily original research reports (e.g., survey/overview/review-type articles,tutorials,conference overviews,and other narrative syntheses),(b) are directtranslations orrepublications of olderwork,or(c)havefewer than5downstream citationsrecordedincurated citationindexes(required forICsVto assemble a non-trivial Evidence Committee).

This procedure offers three advantages. First, it guarantees that each source paper is a field-central object around which substantial citation behavior has already accumulated,rather than a marginal orrarely cited work.Second,by choosing reduces the risk that frontier LLMs have memorized the full text, which is critical for the knowledge-blank protocol in AppendixA.2.

## A.2.Knowledge-BlankCleanroomFact-CheckingProtocol

The knowledge-blank "cleanroom" protocol is designed to ensure that evaluated models cannot rely on parametric memory of source papers in M1sCITEBENcH, but must instead reason over the documents they are given at evaluation time. Intuitively, a paper enters MisCITEBENCH only if a broad panel of strong models collectively "fail' to recognize its internal details, evenwhenexplicitlypromptedtorecall them.

Fact-check probe synthesis via LRM + human curation. For each candidate source paper, we construct N = 10 forensicfact-checkquestionssuch that answeringthem correctlyrequires access tothemainbody or appendices and cannot be solved from title, authors, venue, year, or general background knowledge alone. We follow these design guidelines:

- Questions target specific, non-obvious details: numerical results, ablation outcomes, limitations, cross-subgroup comparisons, key hyperparameters, or subtle qualitative caveats.
- Each question has a deterministic, single ground-truth answer (a number, short phrase, or Boolean) so that correctness is well-defined.
- The answer is supported by a single gold snippet that a human auditor can locate in the full text in a short time.
- Questions are balanced in difficulty, mixing relatively simple pattern-completion probes (e.g., filing in a key number) with more intricate checks that hinge on fine-grained details.
- All questions must be grounded in the content of the source paper itself, not in any paper that the source cites.

IWe exclude editorials, letters, corrigenda, and news-and-views pieces by filtering on publisher-provided article-type metadata and, when ambiguous, by manual inspection.



--- Page Break ---



To construct these probes, we first apply a Large Reasoning Model (LRM; gemini-2.5-pro) to the full text of the candidate paper, including appendices. The LRM is instructed to read the paper sentence by sentence, perform deep reasoning to understand every detail, and then propose 15 candidate fact-check questions together with their canonical answers and supporting snippets. The exact prompt we use is:

```
BibAgent: An Agent Framework for Traceable Miscommunication Detection in Scientific Literature
    -----------------------------------------------------------------------------
    To construct these pboxes, we first apply a Large Reasoning Model (LRM; gemini-2.5-pro) to the full text of the
    candidate paper, including appendices. The LRM is instrumented to read the paper sentence by s between, perform deep
    reasoning to understand every detail, and then propose 15 candidate fact-check questions together with their canonical
    answers and supporting snippets. The exact prompt we use is:

      Fact-check question synthesis prompt

      You will be given the full text of a scientific paper (including any appendices).
      Read the paper carefully, line by line, and use every deep reasoning to ensure
      that you understand every detail of its content.

      Your task is to design 15 fact-check (FC) questions about this paper as training
          to test whether a large language model has been characterized the paper as training
          data  and  truth  ;  knows  its  internal  details.

      Requirements:

      1. Each FC question must have a single, deterministic ground-truth answer.
           The answer must not be vague, subjective, or open-ended. It should be short
           (e.g., a specific number, phrase, or Boolean) so that correctness can be
           checked reliably.

      2. The FC questions must probe details that are specific to this paper.
           Avoid anything that could be guessed from common sense or generic background
           knowledge. Focus on paper-exclusive details such as exact numbers, specific
           experimental configurations, particular subsets, abstraction outcomes, or
           precise verbatim caveats.

      3. The set of 15 FC questions should cover a balanced range of difficulty:
           - some medium-difficulty checks, completing a number in a sentence,
           - some hard-difficulty checks,
           - (e.g., many text + appendix).
           All questions must be strictly painful to the paper; do not introduce
           hallucinated content.

      4. Prefer high-memorization cues: if this paper had been used as part of a
           training set, a model that memorized it should be able to answer these
           questions accurately.

      5. Very important: all FC questions must be derived from the content of this
           paper itself. Do NOT base any question on the content of other papers cited
           in the references.

      Output format:

      Return the 15 FC questions in standard CSV form with the following columns:
      - "Paper Title": the exact title of this paper in English.
      - "FC Question": the fact-check question in English.
      - "Standard Answer": the exact snippet from the paper where the answer appears.
      - "Original Text": the exact snippet from the paper where the answer appears.
      For any mathematical expressions in "Standard Answer" or "Original Text",
      use inline LaTeX with $...$ and ensure that the formulas are completely
      correct and compatible.

      All content in the CSV must be in precise English.

      Paper full text:
      [INSERT PAPER HERE]

      From the 15 LRM-generated candidates, human annotates then select and edit a final set of N= 10 questions per
```

From the 15 LRM-generated candidates, human annotators then select and edit a final set of N = 10 questions per



--- Page Break ---



paper. During curation, annotators (i) verify that each question truly requires full-text access, (i) remove any probe that could plausibly be answered from metadata or general domain knowledge, and (ii) correct the Standard Answer and Original Text fields when necessary.

Gating models and prompt. We probe a fixed, heterogeneous panel of frontier and strong open models: gpt-4o-2024-08-06， 04-mini-2025-04-06， gpt-5-2025-08-07， claude-s0nnet-4-20250514, claude-opus-4-20250514，9 gpt-oss-120b，gpt-oss-20b,Nemotron 3 Nano (30B A3B), Llama-3.3 Nemotron Super 49B v1，Qwen3-235B-A22B-Thinking-2507， Qwen3VL32B Thinking,Qwen3 VL 8B Thinking, Ministral 3 (14B Reasoning 2512)，Magistral Medium, Deepseek-V3.2 (Thinking),DeepSeek-R1-0528,Deepseek R1 Distill Qwen 32B,Deepseek R1 Distill Qwen 14B,Llama 3.1 405B Instruct,andLlama 3.3 70B Instruct.

For each model,we deliberately restrict access to metadata only: title,author list, journal/venue,and publication year. The abstract and full text are never provided to the gating models. We explicitly disable tool usage and web browsing.

Each model receives, for each question, the following fact-check gate prompt.

- System Prompt for Fact-Check Gate You are evaluating whether you already know the internal contents of a scientific article from your training data. You will see ONLY the article's title, authors, journal/venue, and year. You will NoT see the abstract or full text. Then you will be asked a highly specific factual question about the article. Very important: - Do NOT guess. -If youareNoTcertainof theexactanswer basedon whatyoualreadyknow about this paper from pre-training, answer with the single token: UNKNoWN. Only answer with a concrete value if youare sure itexactly matches what appears in the original paper.

## User Prompt for Fact-Check Gate

```
Use, Drop if not exists (Check Gate);

		Article metadata
		Title:    [TITLE]
		Authors: [AUSTHORS]
		Journal: [VENUE]
		Year:     [YEAR]

		Fact-check question
		[QUESTION_i]

		Instructions
		If you are certain you know the exact answer from your internal knowledge
		of this paper, answer with a short phrase or number.

		Otherwise, answer with the single token: UNKNOWN.

```

model m's response to question i.



--- Page Break ---



- Numeric answers. If a is numeric, we parse r" (u) as arealnumberwheneverpossibleand countit ascorrectif

$$\frac { | r _ { i } ^ { ( m ) } - a _ { i } | } { \max ( 1 , | a _ { i } | ) } < 0 . 0 1 .$$

- Textual answers. If a is textual, we do not rely on brittle string equality. Instead, we use an independent LLM grader (gpt-4o-2024-08-06) that receives both thegold answer and the model's response and decides whether they are semanticallyequivalent.Thegradingpromptis:

## Grading Prompt

You are grading whether two short answers express the same factual content.

```
Gold answer:    "[GOLD_ANSWER]"
  Model answer:    "[MODEL_ANSWER]"

```

If，ignoring superficial differences in wording,the two answers refer to the same specific fact with the same level of specificity, respond with YES. OtherwiserespondwithNo.

Respond with exactly one token: YES or NO.

A textual response r （m） is marked correct if and only if the grader returns YES.

A candidate paper is admitted into MIsCITEBENCH if and only if every model in the panel fails all probes, i.e.,

$$\forall m \in \mathcal { M } , \ \sum _ { i = 1 } ^ { N } 1 [ r _ { i } ^ { ( m ) } \text { is correct} ] = 0 .$$

journal and time window,repeating the procedure until a clean paperis found or the candidate pool is exhausted.

## A.3.Dual-TierAdversarialMiscitationGenerationandValidation

This section details how we generate and validate adversarial miscitations grounded in the five-category taxonomy described in Section 2.1. The goal is to create instances that are (i) realistic, (i) taxonomy-pure (each miscitation belongs

LRM generation prompt and output schema.Given a source paper B, we provide a Large Reasoning Model (gemini-2 .5-pro) with the full paper, including all main sections and appendices, together with the detailed definitions of the five miscitation categories. The model is instructed to first perform extremely deep reading and then, for each category,synthesizebothmoderate andvery difficult miscitations.

The core generation prompt (simplified for presentation) is:

## Prompt to LRM for miscitation synthesis.

We are constructing a dataset of diverse miscitation examples to evaluate automatic miscitation detection systems.

You will be given the FULL TEXT of a source paper (including appendices) and the definitions of 5 miscitation categories. First， read the paper slowly and carefully， sentence by sentence, and use very deep reasoning to ensure that you understand its methods, results, limitations, and nuanced details.

Then, for EACH of the 5 miscitation categories, you must create 5 miscitation



--- Page Break ---



- examples that (incorrectly） cite this paper: 3examplesshouldbesinglesentencesorshortparagraphsthatareclearly wrong for a careful reader who deeply understands the paper，but not so trivialthat they can be spotted at a glance. - 2 examples should be long, complex sentences or slightly longer paragraphs rely on subtle, easily overlooked details of the paper, such that even domain experts or the original authors would need to think carefully before identifying the error. Additional constraints: - Different scenarios under the same category should be diverse. Cover as many distinct ways of committingthat type of miscitation as possible. -Differentcategories must remain wellseparated.Eachdesignedexample should clearly belong to exactly ONE miscitation category under the taxonomy, with no ambiguity or overlap. -For EVERY miscitation example, you must also provide: *Explanation:a clear English explanation of why this is a miscitation and how it instantiates the target category. *Correct Statement:a corrected citing sentence or short passage that would describe the source paper accurately. * Original Text: the exact snippet(s） from the source paper that grounds your judgment (i.e.， what the paper actually says). Read the source paper deeply enough to avoid being misled by possible typesetting or formatting errors. -Very important: miscitation content must be about THIS source paper.Do NOT base any miscitation on the content of other papers cited in its references. Output format: Return all 25 designed miscitations (5 categories * 5 examples） in CsV form with the following columns: "Miscitation": the incorrect citing sentence or short paragraph. "Explanation": why this is a miscitation, in clear English. -"Correct Statement": a corrected version that would cite the paper properly. "Original Text": the supporting snippet(s) from the source paper. "Miscite Type": one of {Citation Validity Error, Content Misrepresentation Error, Scope Extrapolation Error, Evidence Characterization Error, Attribution&amp; Traceability Error}. "Difficulties": one of {SURFACE，DEEP}，where SURFACE indicates a moderate, more local error, and DEEP indicates a very difficult, globally subtle error. All content must be in precise English. Ensure that each example strictly matches its assigned miscitation type and difficulty level. Source paper full text: [INSERT PAPER HERE] Miscitation taxonomy: [INSERT 5 CATEGORY DEFINITIONS HERE]

This prompt yields,for each source paper, 25 candidate miscitation rows covering the full taxonomy: three SURFACE



--- Page Break ---



Original Text,Miscite Type,and Difficulties. We perform schema validation and reject any row where the generated Mi scite Type is inconsistent with the textual description in Explanation.

Post-processing and CSV representation. The raw LRM outputs are parsed into a standardized CSV representation. We normalize category labels to the five taxonomy names, collapse minor variations in difficulty tags into SURFACE vs. DEEP, and enforce basic well-formedness constraints (non-empty fields, length limits, and valid category labels). Instances that repair.

Independent LRM consistency check. Each candidate miscitation is then re-evaluated by an independent LRM with a different architecture and training history (gpt -5 . 1-Extended-Thinking). For each row, the independent model receives:

- the full source paper,
- ·the candidate Miscitation sentence/paragraph,
- the proposed Miscite Type and Difficulties,
- the Original Text snippet, and
- the original Explanation and Correct Statement.

The independent LRM is asked to (i) decide whether the candidate is in fact a miscitation of the source, (i) assign the most appropriate taxonomy category, and (ii) provide its own free-form explanation of the error and a corrected citing statement.

Wethen applytwo automaticfilters:

- Category agreement. If the independent model assigns a different primary miscitation type than the original Mi scite Type, the instance is fagged for removal or manual repair.
- ·Explanation alignment. We again use gpt-4o-2024-08-06 as a semantic grader to compare the independent semantically equivalent (same mechanism, same primary error) are retained.

Examples that fail either check are either edited and re-validated or dropped entirely.

Human expert validation.Finally, we subject every source paper and its 25 candidate miscitations to rigorous human review by domain experts. We recruit a panel of PhD students, researchers, and senior practitioners spanning all 21 high-level disciplines covered by the 254 JCR subject categories. Collectively, their expertise covers the full set of subfields represented in MISCITEBENCH.

For each source paper, we assign 3-4 experts whose research area matches the corresponding high-level discipline (e.g., Clinical Medicine, Computer Science, Social Sciences). Each expert is given the full source paper and the 25 miscitation rows and asked toperform cross-validationunder thefollowing criteria:

1. Is it truly a miscitation? Does the Mi scit at i on sentence or paragraph in fact misrepresent the source paper, and does the stated Explanat ion accurately and fully capture the reason it is wrong?
2. Taxonomy alignment. Given the definitions in our five-category taxonomy, does the assigned Mi scite Type correspond to the primary error mechanism? Could a reasonable annotator confidently place this instance in exactly this category?
3. paper that justify the error diagnosis (and, for corrected statements, their validity)?



--- Page Break ---



4. Corrected statement accuracy. Is the Correct Statement factually consistent with the source paper and free from new miscitation issues?

A miscitation instance is retained in M1sCITEBENCH only if all assigned experts agree that it satisfies the criteria above. instanceis eitherrevised and re-submitted tothesamevalidationprotocolor discarded.

After this multi-stage pipeline—LRM generation with deep reading, independent cross-model consistency checking, and stringent domain-expert cross-validation—we obtain the final set of 254 source papers × 5 categories × 5 instances per category, for a total of 6,35O high-quality miscitation cases used in M1sCITEBENCH.

## B. Taxonomy Annotation Protocol

This appendix provides the full details of the expert annotation study referenced in Section 2.1. The goals of this study are twofold: (i) to test whether the five-category taxonomy is empirically usable and complete across disciplines, and (ii) to quantify how reliably independent experts can reproduce each other's judgements when constrained by the Dependency PrecedenceRule.

## B.1. Sampling Strategy and Annotator Panel

Instance selection. From the full M1sCITEBENCH benchmark of 6,350 miscitation instances, we draw a stratified sample of N=500 cases for manual validation.Stratification is performed jointly over:

1. Taxonomy category: we maintain approximately equal representation of the five error types (Citation Validity, Content
2. Discipline: we preserve the distribution over the 21 high-level disciplines used in M1sCITEBENCH construction (e.g., Agricultural Sciences, Clinical Medicine, Computer Science, Social Sciences, Visual &amp; Performing Arts), so that no single field dominates the sample.

This design ensures that the annotation study probes both the breadth of scientific domains and the full error-code space, rather than concentrating on a narrow subset of easy or homogeneous instances.

Annotator qualifications.Each instance is independentlylabeled by 3 experts with doctoral-level or advanced graduate trainingin a subfield relevant tothe sourcepaper.Werestrict assignment sothat:

- every annotator has prior experience with reading and evaluating peer-reviewed scientific articles in the corresponding discipline, and
- no annotator is asked to label instances from a field outside their demonstrated area of expertise.

Experts are blind to the synthetic origin of MisCITEBENCH and are instructed to treat each instance exactly as they would when reviewing a real manuscript.

## B.2.AnnotationMaterials andUserInterface

For each candidate miscitation instance, annotators are provided with a compact but fully contextualized bundle:

- Source-side context: the title, abstract, and gold supporting excerpt (i.e., the span in the source paper that the miscitationwasconstructedtodistort).
- Citing-side context: the expanded citing window Sexpanded (the citing sentence plus its immediate neighbors), matching the context used by BIBAGENT during verification.
- Taxonomy reference: the definitions of the five categories, including their diagnostic litmus questions and short examples, identical to those in Section 2.1.



--- Page Break ---



The annotation interface is a structured form that guides experts through the same logical decision path used by B1BAGENT. For each instance, the interface:

1. presents the citing context and source excerpt side-by-side,
2. displays the five taxonomy categories with their litmus questions in a collapsible panel, and
3. enforces the Dependency Precedence Rule via a hierarchical selection widget (described below).

## B.3.DecisionProcedureandDependencyPrecedence

Annotators are explicitly instructed to mimic the stepwise verification process a careful reviewer would perform. The interfaceenforcesthefollowingsequence:

1. Attribution &amp; Traceability check. Determine whether, given the citation metadata, a reader could reliably locate and identify the correct source (Attribution &amp; Traceability Error). If an Attribution failure is present (e.g., ghost citation, hopelessly ambiguous metadata), annotators select this label and no further categories can be chosen.
2. Citation Validity check. If the citation is traceable, decide whether the source itself remains valid as scientific evidence (Citation Validity Error), e.g., retracted or misused secondary source. If so, this label is selected and lower levels are disabled.
3. Content Misrepresentation check. If the source is valid, compare the citing context to the source excerpt and decide whether the citing text faithfully represents the factual content (Content Misrepresentation Error).
4. Scope Extrapolation check. If content is correctly represented, decide whether the citing text applies an otherwise
5. 5.Evidence Characterization check.Finally, decide whether the citing text mischaracterizes the logical type or strength of the evidence (Evidence Characterization Error), e.g., treating correlational results as causal or overstating statistical certainty.

This procedure operationalizes the Dependency Precedence Rule described in Section 2.1: once an annotator records a failure at a higher level (e.g., Attribution), all lower levels (Validity, Content, Scope, Evidence) are automatically grayed out and cannot be selected for that instance. Conversely, if no failure is detected at any level, the annotator records the instance asNomiscitation.

In addition to the five primary taxonomy labels, the interface provides two auxiliary options:

- Other: the annotator judges that there is a genuine miscitation, but it does not fit any of the five categories.
- Uncertain: the annotator cannot confidently decide due to ambiguity or insufficient information.

For each chosen label (including "Other"' and "Uncertain"), annotators supply a short free-text rationale explaining their decision. These rationales are later used during adjudication and for qualitative error analysis.

## B.4.Agreement Measurement

To quantify reproducibility, we compute pairwise Cohen's k among the three annotators over the five taxonomy labels only, ignoring instances labeled as "Other" or "Uncertain" by any annotator.2 For annotators a and b, Cohen's k is defined as:

$$\kappa = \frac { p _ { o } - p _ { e } } { 1 - p _ { e } } ,$$

where p。 is the observed label agreement and pe is the expected agreement under chance, computed from the empirical label marginals.

2We exclude "Other" and *"Uncertain" from the primary agreement analysis because they are by design fallback categories; their frequency is reported separately.



--- Page Break ---



Across annotator pairs, we obtain an average K = 0.73, which falls in the "substantial" agreement range under conventional benchmarks. This indicates that, given the same source and citing contexts and a shared taxonomy, independent experts largely converge on the same primary error category.

The marginal usage rates of the fallback options are low: "Other"is selected in 4.2% of annotations and "Uncertain"in 3.6%. These small rates, together with the substantial k, provide empirical evidence that:

1. the five-category taxonomy is sufficiently expressive for the M1sCITEBENCH corpus, and
2. 2.the operationallitmus questionsmake categoryboundaries clear enoughforreproducible annotation.

## B.5.Adjudication andFinalLabels

After individual annotation, we perform a structured adjudication step to obtain a single gold label per instance:

- label.
- Complete disagreement or fallback use. If all three annotators select different categories, or if any annotator chooses "Other" or "Uncertain", the instance is escalated to a fourth senior annotator.

Thesenior annotatorhasfull access to:

- 2.thethreeannotators'labels,and
- 3.their free-text rationales.

They then assign a final label consistent with the Dependency Precedence Rule, optionally revising the instance text if a clear typographical or formatting error is discovered. In practice, adjudication rarely required reconsidering the underlying taxonomy itself: no new error categories were requested, and all disputed cases could be resolved by clarifying which litmus

Taken together, the low reliance on"Other"and "Uncertain", the substantial inter-annotator agreement, and the lack of new failure modes captured in MIsCITEBENCH and operationally precise enough to be applied reproducibly across disciplines.

## C. Document Parsing and Citation Mapping Details

The Document Parser and Citation Mapper (DPCM) normalizes heterogeneous inputs (LTEX, XML/HTML, and PDFs) into a single hierarchical Markdown representation. This representation preserves the discourse skeleton of the paper—-headings, paragraphs, math, figures/tables, and citation anchors—so that downstream verification always operates on a traceable, format-agnostic substrate. This appendix details (i) markup-based normalization, (i) PDF parsing via image-based layout serialization, (i) the Extraction Verifier, and (iv) citation mapping.

## C.1. Markup-Based Normalization

For ITEX and XML/HTML inputs, DPCM constructs an intermediate abstract syntax tree (AST) and then projects it into Markdown while deliberately retaining only semantics that matter for citation auditing.

Macro handling and structural projection. We expand standard inline macros such as \emph, \textbf, and not change logical structure.Sectioning commands （\section,\subsection,etc.） are converted into Markdown headings (#, ##, ###), while lists,display math, and inline math are serialized as Markdown lists and $...$ / $$...$$ blocks. Cross-references (\ref,\eqref, etc.) are preserved as literal text so that equation, figure, and table numbering can later be checked for consistency.



--- Page Break ---



Citation rendering and anchoring. Citation commands in markup (\cite, \citep, \citet and style-specific variants)areprocessedin two coupledlayers:

1. Surface rendering. Using the document's bibliographic style configuration (e.g., numeric, author-year/APA, Chicago),we re-render each citation into the same surface form that a compiled PDF would produce: for example,\citep{Smith2020,Brown2019} becomes "(Smith,2020;Brown &amp; Brown,2019)"under APA-style readers, which is crucial for later LLM-based reasoning.
2. Stable internal anchors. In parallel, DPCM attaches an internal anchor to each rendered citation that records the originating citation keys and their order. These anchors are not shown in the surface Markdown, but they form a lossless mapping from each inline citation occurrence back to the corresponding bibliography entries. Citation mapping (SectionC.4)laterconsumes these anchorstobuildsentence-levelcitationgraphs,whileACsV andICsVoperate purely on the human-readable surface text.

The result of markup normalization is a hierarchical Markdown document that faithfully reflects the compiled reading experience, while still exposing a machine-tractable citation backbone.

## C.2.PDF Parsing via Image-Based Layout Serialization

Text-based PDF extraction often yields broken reading order, missing math, and unreliable treatment of figures and tables. For PDFs, DPCM therefore uses an explicit image-based pipeline that delegates layout reconstruction to a multimodal model and then repairs cross-page boundaries.

## C.2.1.PAGERENDERINGANDPAGE-LEVELTRANSCRIPTION

a concise systemprompt that specifies theMarkdown serializationrules.

The system prompt used for page-level transcription is:

```
Please accurately convert the main body text in the image into markdown.
  Use $...$ for inline formulas and $...$ for display formulas.

  Requirements:
  1. Preserve the original wording exactly. Do NOT paraphrase, add, or omit text.
  2. Extract only main body text.
     - Ignore translations and graphical elements
     - Keep captions whose text starts with "Figure", "Table", "Fig.", or "Tab."
  3. If the image conta'ins tables, convert them fairly into markdown tables.
  4. Remove headers, footers, page numbers, and sidebars that are not part of
     the main body.
  5. Do not call any external tools; rely only on your visual understanding.
  6. If the image contains no readable text, output: null

```

Themodel returnsMarkdownfor the page;if it wraps the content inside a code fence,we strip thefence and retain only the inner Markdown. This gives us a sequence of per-page Markdownfragments that already approximate the correct reading order, with headings, paragraphs, displayed math, inline math, figure and table captions, and inline citations rendered as they appear on the page.

## C.2.2.CROSS-PAGE BOUNDARYREPAIR

Page-level OCR and transcription inevitably break some sentences across page boundaries.DPCM therefore applies a dedicated cross-page repair pass before any structural verification or citation mapping.

We maintain two parallel views of each page: (i) the original page-level Markdown output, and (i) a tagged version used for



--- Page Break ---



debugging, in which we mark potentially incomplete beginnings or endings using lightweight heuristics.

Incomplete head/tail tagging. For each page, we inspect the first and last non-empty lines. A line is considered a complete ends with a citation or reference pattern (e.g., "[12]"), or is a plausible standalone heading or caption. We consider the first content line to be a complete start if it looks like the beginning of a new sentence or block (e.g., capitalized heading, list item, or math environment) rather than a continuation.

If the tail of a page fails these checks, we tag it with &lt;INCOMPLETE\_END\_Pn&gt;; analogously, if the head of the next page looks like a continuation (lowercase start, conjunctions such as "and", "but", "however", leading bracket, etc.), we tag it with &lt;INCOMPLETE\_START\_Pn&gt;. These tags do not change the content but mark candidate boundaries for repair.

procedure.For each adjacent page pair, we:

- Split each page into paragraphs separated by blank lines.
- Separate figure/table captions from main text, so that caption-only paragraphs are appended without being merged into running prose.
- Examine the last main-text paragraph of page n and the first main-text paragraph of page n+1.

If the tail paragraph is incomplete and the head paragraph does not resemble a new heading or section, we attempt to repair the boundary:

- appropriate.
- 2.Direct continuation.If the head starts with a lowercase letter,discourse connective (and,but,however, therefore,which, that, because, etc.), or an opening bracket, we join the two paragraphs with a space, treating them as a single sentence that crossed the page break.

If neither heuristic confidently applies but the tail paragraph is clearly incomplete and not a caption, we fall back to a minimal LLM-based boundary repair step that edits only the ambiguous junction.

LLM-based boundary repair. For hard cases, we send the last paragraph of page n and the first paragraph of page n+1 to gpt-4o-2024-08-06with a dedicated system prompt:

```
You repair cross-page sentence breaks in markdown text extracted from a
    scientific PDF. You are given:

    - PREV: the tail paragraph of page N
    - NEXT: the head paragraph of page N+1

    They may contain:
    - a sentence split across the page break,
    - duplicated fragments, or
    - a word split by a hyphen.

    Your task:
    - Minimally fix the boundary so that the text reads as a single continuous
      document.
    - Do NOT invert new content or change meaning.
    - Do NOT drcor valid content except for exact duplicates.
    - You may:
```



--- Page Break ---



```
- move tokens between PREV and NEXT,
      - remove duplicated fragments,
      - join hyphenated words split across the boundary.

  Output exactly in this format:

  PREV_FIXED:
  <fixed text for the previous-page tail>
  ---
  NEXT_FIXED:
  <fixed text for the next-page head>

```

We parse PREV\_FIXED and NEXT\_FIXED from the model output and adopt them only if the boundary has changed in a way that improves continuity (e.g., duplication removed, sentence completed). Otherwise, we keep the original paragraphs This design ensures that the LLM operates as a local repair operator, not as a free-form rewriter of the document.

After iterating over all boundaries, we remove debug tags &lt;INCOMPLETE\_START\_Pn&gt; and &lt;INCOMPLETE\_END\_Pn&gt; and normalize whitespace,yielding a single merged Markdown file that reflects the visual layout and reading order of the PDF while repairing cross-page sentence breaks.

## C.3.Extraction Verifier

Once the merged Markdown is available, the Extraction Verifier performs a multi-level audit to detect structural and bibliographic inconsistencies before citation reasoning. The verifier combines deterministic checks with targeted LLM-based inspection.

Level 1: deterministic structural checks. We parse the Markdown into a lightweight document tree and enforce basic invariants:

- ·Heading progression. Heading levels must not jump by more than one level (e.g.,#→ ## → ### is allowed; # →→
- are checked for monotone, mostly contiguous sequences. Small gaps are tolerated, but long stretches of missing or duplicated numbers trigger a warning.
- Citation index sequences. For numeric styles, we extract all integers appearing in citation-like patterns (e.g., "[3]", "[3, 5, 9]", "[3-5]") and verify that the global sequence is roughly monotone and dense. Large gaps (e.g., no references between [5] and [20]) or frequent out-of-order jumps signal potential parsing failures, such as skipped bibliography segments ormis-ordered text blocks.

For each violation, the verifier records the surrounding lines and the page range where the anomaly occurs.

Level 2: localized re-parsing. When Level 1 identifies a likely structural discontinuity that aligns with a small set of pages (e.g., a break in equation numbers between pages 7 and 8), we re-run the PDF-to-Markdown conversion only on those against the original to detect missing lines, duplicated blocks, or altered reading order. If the re-parsed fragment resolves the anomaly (e.g., restores a missing equation or bibliography block),we splice it into the global document; otherwise,we keep the original and proceed to Level 3.

decide (e.g., text density drops abruptly without clear structural markers), we invoke a light semantic audit. We provide gpt-4o-2024-08-06 with the Markdown snippet around the anomaly and a succinct description of the expected structure, asking whether the snippet appears truncated, duplicated, or out-of-order. A representative prompt is:



--- Page Break ---



```
BinAgent: An Agent Framework for Traceable Miscommunication Detection in Scientific Literature
        -----------------------------------------------------------------------------
        You are auditing markdown extracted from a scientific paper.

        You are givea a short markdown segment and a brief description of the
        surrounding document structure (e.g., "between Section 3.2 and Section 3.3").

        Decide whether the segment shows signs of extraction error:
        - missing lines or sentences,
        - duplicated paragraphs,
        - obvious reading-order errors (e.g., a caption in the middle of a sentence).

        Answer with one of:
        - OK
        - SUSPICIOUS_MISSING
        - SUSPICIOUS_DUPLICATE
        - SUSPICIOUS_ORDER

        Then, in one short sentence, explain your choice using only evidence that is
        visible in the provided markdown.

        
```

Segments labeled as suspicious are either re-parsed again with tighter crops or flagged as low-confidence regions for downstream modules (ACSV/ICSV) and, if needed, for manual inspection. In practice, this three-level verifier reduces gross extraction failures (e.g., missing sections, mis-ordered columns) while keeping the pipeline predominantly deterministic and auditable.

## C.4. Citation Mapping

Given a structurally verified Markdown document, the citation mapping component constructs a sentence-level citation graph that is consumed by CSAC, ACSV, and ICSV. The goal is to map each inline citation span in the body text to one or more normalized bibliography entries, while preserving the original surface style.

Inline citation detection.We first identify citation spans in the Markdown using style-agnostic patterns.The detector considers threefamilies:

- ·Numeric citations, such as “[12]", “[3, 5, 9]", “[3-5]", and inline variants like “(see also [7])".
- ·Author-year citations, such as "(Smith, 2020)", ""Smith (2020)", and grouped forms like "(Smith, 2020; Brown &amp; Lee, 2019)".

By scanning the entire document, we infer the dominant citation style (numeric vs.author-year vs. note-based) from containing sentence(using punctuation-based segmentation with list/heading safeguards),yielding a preliminary mapping fromsentencestounnormalizedcitationstrings.

Bibliography parsing. We then isolate the bibliography section (or sections) by detecting headings such as "References", "Bibliography", or style-specific variants. Each bibliographic entry is parsed into a normalized record containing at minimum: canonical author list (last names and initials), publication year, title tokens, venue/journal name, and any explicit identifiers (DOI, arXiv ID, PubMed ID). For markup-based inputs, we prefer the original \bibitem or BibTeX metadata; for PDF-only inputs, we rely on typography cues (hanging indentation, numbering, bullet markers) combined with pattern-based parsing.

Citation-to-entry alignment.Finally, we align inline citation spans to bibliography entries:



--- Page Break ---



- Markup inputs. When the document originates from LTEX or XML/HTML, we use the internal anchors described earlier to directly map each inline citation occurrence to a set of bibliography records, with no string matching required. Thismapping isexact and order-preserving.
- PDF-only inputs, numeric style. We map numeric indices in citations (e.g., "[7] or "[3-5]") to positions in the parsed bibliography list, taking into account style-specific conventions (e.g., whether numbering restarts in supplements). Ranges and grouped citations are expanded into individual edges (e.g., "[3-5]" yields links to 3, 4, and 5).
- score between this tuple and each candidate bibliography entry,based on overlap of normalized last names,year equality, and title token similarity. The highest-scoring candidate above a threshold is selected; ties and sub-threshold cases are flagged as ambiguous.

In ambiguous or noisy cases (e.g., partial author lists, missing years), we use a lightweight LLM-assisted disambiguation step:weprovide thesurfacecitation string and a small set of candidatebibliography entries and askthemodel toselect the best match or to abstain if none is appropriate. This step is constrained to choose from explicit candidates and does not fabricate new references.

The final output of citation mapping is, for each sentence including intext citation(s) in the document, a set of resolved citation edges pointing to normalized metadata records (title, authors, year, venue, DOl). This structure is the entry point for CSAC, which determines source accessibility, and for ACSV/ICSV, which perform taxonomy-aligned miscitation verificationontopofafullytraceablecitationgraph.

## D.ICsVImplementationDetails

This appendix documents the concrete implementation of the Inaccessible Cited Source Verifier (ICsV) and its Evidence Committee mechanism. ICSV targets the strict paywall regime: the full text of the cited source B is unavailable, so verificationmust begroundedin auditabledownstreamevidencerather thanspeculativereconstruction.Wetherefore(i) extract a claim-preserving paraphrase of what the citing paper A attributes to B, (i) extract analogous attributions to B from multiple open-access downstream citers, (ii) organize these attributions into coherent aspects via LLM-based semantic clustering, (iv) assign field-normalized influence weights across heterogeneous venue types (journal / conference / preprint), and (v) compute a reliability-aware consensus verdict with calibrated confidence and principled abstention.

Unless otherwise noted, allICSV LLM calls use gpt-4o-2024-08-06.We use gpt-4o-2025-08-06 only for the semantic clustering step (Section D.4) to improve partition stability on long claim lists.

## D.1.DownstreamCommitteeRetrieval andWitnessVerification

Given a paywalled cited source B,CSAC provides a resolved metadata snapshot(DOI when available; otherwise title, author list, venue, year). ICsV then constructs an open-access witness set Copen of downstream citers that reference B and have retrievable full text.

Primary citation-graph retrieval. We query a curated open citation index (OpenAlex as primary; Crossref as DOI/metadata fallback) to enumerate works that cite B. We de-duplicate by DOI and canonical title normalization (lowercasing, punctuation stripping, whitespace collapse) and discard non-scholarly records (e.g., editorial notes) using venue/type metadatawhenavailable.

Open-access eligibility and full-text acquisition.A candidate citer p enters Copen only if (i) a full-text URL is available (publisher OA, institutional repository, or vetted preprint server), and (ii) the downloaded full text can be parsed by DPCM intostructuredMarkdownwithintact citation anchors.

Witness validity check (must explicitly cite B in-text). For each candidate citer p, we verify that p contains at least one explicit in-text citation mention to B. We accept a mention if any of the following match robustly: (i) DOI match, (ii) high-similarity title string match, or (ii) bibliography-entry match followed by an in-text anchor pointing to that entry. Candidates that do not pass this in-text witness check are discarded to prevent"false witnesses"created by noisy citation graphs.



--- Page Break ---



No premature skipping. ICsV never "skips" a paywalled citation after retrieval. If witnesses are weak or contradictory, the system returns UNDECIDABLE with an explicit reliability diagnosis (Section D.7).

## D.2. Context-Aware Citing Claim Paraphrase (from Paper A)

The first step is to construct cA: a claim-preserving paraphrase of what A attributes to B at the citation site. Importantly, our implementation does not ask the model to"rewrite the single main claim"(which invites summarization or abstraction). Instead, it performs a tight paraphrase of the cited sentence, with one permitted transformation: resolve pronouns and implicit references into explicit mentions while preserving all qualifiers, modality, and scope.

Window expansion (iterative; no skipping). Let sA be the in-text sentence in A that cites B. We start from a minimal local window and expand only when necessary:

$$W _ { A } ( r ) = \text {sent} ( A , i - r ) \oplus \cdots \oplus \text {sent} ( A , i ) \oplus \cdots \oplus \text {sent} ( A , i + r ) ,$$

where i is the index of sA and r is the radius (default start r=1). If the model returns INSUFFICIENT\_CONTEXT,we increment r ← r + 1 and retry, continuing until a stable paraphrase is produced. We cap expansion by paragraph boundaries; if the paragraph is still insufficient, we extend to adjacent paragraphs in the same section.

Stability criterion. To avoid oscillating paraphrases under larger windows, we require two consecutive radi to produce paraphrases that are identical after normalization (whitespace collapse; punctuation normalization) or have semantic similarity above a high threshold (measured by a sentence embedding cosine similarity). The earlier paraphrase is then fixed as CA.

## Prompttemplate(claim-preservingparaphrase).

## SystemPrompt

```
You are an expert scientific copy-editor and verifier.
    Your job is to produce a claim-preserving paragraph of a specific sentence that cities
        a prior paper B. Do NOT summarize, generalize, or add new claims.
    Preserve all qualifiers (e.g., "may", "suggest", "in our setting"), all scope
        constraints (population/task/conditions), and all numerical content.
    The only required transformation is to resolve pronouns and implicit mentions into
        explicitifiers, using the provided context.

```

## User Prompt

```
[User.From(pom)]

            
            [Context window W_A]
            {W_A}

            [Target sentence s_A that contains the in-text citation to paper B]
            {s_A}

            Instructions:
            1) Paragraphs s_A as closely as possible (claim-preserving).
            2) Resolve pronouns/implicit references using W_A (e.g., "this method" -> the named
                method).
            3) Keep modality, qualifiers, and scope exactly Faithful to s_A.
            4) Do NOT mention citation markers, citation numbers, authors, or years.
            5) Output ONE sentence only.
            6) If the referent needed to resolve pronouns is not recoverable from W_A, output:
            INSUFFICIENT_CONTEXT

```



--- Page Break ---



## D.3.Witness ClaimExtraction (fromEachDownstream Citer)

Selecting explicit mention sites. For each witness p, we locate every sentence sp whose in-text citation anchor resolves to B (via DOI/title/bibliography match as in Section D.1). For each such sp, we run the same claim-preserving paraphrase procedure as Section D.2, producing a witness claim ct) for mention t. Within a witness paper, we de-duplicate claims (t) using high-similarity filtering to avoid overweighting repeated boilerplate mentions.

Outcome.This yields a multi-set of witness claims

$$\mathcal { C } _ { B } = \{ ( c _ { 1 } , \text {src} ( c _ { 1 } ) ) , \dots , ( c _ { m } , \text {src} ( c _ { m } ) ) \} ,$$

where each ce is a claim-preserving paraphrase attributed to B and src(ce) denotes the source witness paper that produced it.

## D.4. LLM-Based Semantic Clustering and Evidence Statement Distillation

The goal is to organize CB into coherent "aspects" of B (e.g., method, dataset, empirical finding), then distill each aspect into a canonical evidence statement e. In our implementation, we do not use embedding-based agglomerative clustering, because choosing thresholds and cluster counts is brittle across fields and can merge distinct aspects of B into the same cluster.Instead, we perform direct semantic clustering with an LLM,which is both more controllable (via explicit constraints)and morerobust to domain shift.

## D.4.1.SEMANTIC CLUSTERING PROMPT (LLM CLASSIFIER)

We use gpt -4o-2025-08-06 to cluster witness claims into non-overlapping groups {G}§=1. The prompt is designed parsing.

## System prompt (semantic clustering).

You are an expert scientific librarian. You will receive a list of short, claim-preserving sentences that different papers attribute to a paywalled paper B.

Task:cluster these sentences into semantically coherent aspects of B. Each cluster must represent ONE aspect (e.g., one method contribution, one dataset， one key empirical finding, one theoretical claim). DoNoT merge two distinct aspects just because they are topically related.

## Constraints:

- -Every claim must belong to exactly one cluster.
- -If a claim is vague, place it into the closest cluster only if consistent; Return JSoN only (no prose）.
- Clusters should be as few as possible, but no cluster may contain claims that are substantively about different contributions/aspects.

## User prompt.

```
Paper B (metadata):
  Title: {title_B}
  Year: {year_B}
  Venue: {venue_B}

  Witness claims about B (each has an ID):
  1) {c_1}

```



--- Page Break ---



```
BbAgent: An Agentic Framework for Traceable Miscitation Detection in Scientific Literature

        2) {c_2}
        ...
        m) {c_m}

        Output JSON with the following schema:
        {
          "clusters": [
            {
              "cluster_id": "C1",
              "cluster_name": "short aspect name",
              "aspect_summary": "one-sentence description of the shared aspect",
              "claim_ids": [1, 7, 12]
            },
            ...
          ]
        }

        Rules:
        - cluster_name must be <= 8 words.
        - aspect_summary must be exactly one-sentence.
        - Do not invert content not present in the claims.
```

## D.4.2.EVIDENCESTATEMENT DISTILLATION (PER CLUSTER)

For each cluster G§, we distill a canonical evidence statement e; that represents the shared content as attributed by the community.This step uses gpt-4o-2024-08-06.

```
community. This step uses gpt-4o-2024-08-06.

       System prompt (evidence destination).


       You are an expert scientific verifier.
       You will see multiple claims that different papers attribute to a paywalled
       paper B about the SAME aspect. Your job is to write ONE canonical evidence
       statement that captures only their overlap.

       Requirements::
       - One sentence only.
       - Include critical qualifiers (scope, conditions, uncertainty).
       - Preserve numerical quantities if present and consistent.
       - If claims conflict, produce a conservative statement that refLECTs only
         what is common, and explicitly hedge (e.g., "is reported to", "suggests").
       Do NOT add new facts.

```

```
UserPrompt:

    Paper B (metadata):
    Title: {title_B}

    Cluster {cluster_id}: {cluster_name}
    Claims in this cluster:
    - {c_a}
    - {c_b}
    ...

    Write ONE sentence as the canonical evidence statement e_j.
```



--- Page Break ---



Provenance. For traceability, we store for each ej the full set of contributing claim IDs and their source papers. All downstream weighting and voting operates on unique witness papers per cluster (Section D.5), preventing repeated mentions from the same paper from inflating support.

## D.5.Field-Normalized Influence Weights Across Journals, Conferences, and Preprints

Each evidence statement is only as credible as its witnesses. However, raw citations and venue prestige vary drastically across fields and publication years, and venue types differ (journals vs. conferences vs. preprints). We therefore compute a unified influence score Z(p) for each witness paper p, combining (i) paper-level influence within its field-year and (ii) venue-level standing within its field.

## D.5.1.PAPER-LEVEL CITATIONPERCENTILE(ALLVENUE TYPES)

$$C _ { n o r m } ( p ) = R a n k _ { \% } ( C i t e ( p ) \, | \, F i e l d ( p ) , Y e a r ( p ) ) .$$

To reduce heavy-tail instability, we winsorize citation counts within each field-year at the 99th percentile before ranking.

## D.5.2.VENUE-LEVEL STANDING PERCENTILE (TYPE-AWARE BUT UNIFIED OUTPUT)

We define a venue standing percentile Vnorm(p) E [O, 1] based on the venue type:

the journal's subject category:

$$V _ { n o r m } ( p ) = J _ { n o r m } ( p ) = R a n k _ { \% } \left ( I F ( p ) \ | \ J C R \_ F i e l d ( p ) \right ) .$$

Conferences / proceedings.  Conferences typically lack JCR impact factors, but they are indexed with venue-level standing signals (e.g., proceedings series metrics, venue citation rates). We compute a robust proxy in two stages:

$$V _ { n o r m } ( p ) = R a n k _ { \% } \left ( M _ { c o n f } ( v ) \ | \ F i e l d ( p ) \right ) ,$$

where v is the conference venue (or proceedings series) and Mconf(v) is defined by the best available signal in descending priority:

$$M _ { \text {conf} } ( v ) = \begin{cases} \text {venue metric percentile from an index (e.g., CityScore/SJR)} \text { if available,} \\ \text {two-year venue citation rate } \frac { \text {City2Y(v)} } { \text {Works2Y(v)} } \text { from the same index,} \\ \text {fallback: long-run venue citation rate } \frac { \text {CityAll(v)} } { \text {WorksAll(v)} } . \end{cases}$$

This design anchors conference standing in the indexing institution's venue-level ranking signals when present, and otherwise in a conservative,field-normalized citation-rate proxy that is stable under sparsity.

Preprints. Preprints are not peer-reviewed venues, yet they can be influential. We therefore compute a repository-level standing percentile and apply a conservative discount to reflect the absence of formal peer review:

$$V _ { n o r m } ( p ) = \rho _ { p r e } \cdot R a n k _ { \% } ( M _ { r e p o } ( r ) \, | \, \text {Field} ( p ) ) ,$$

where r is the preprint repository (e.g., arXiv/bioRxiv/medRxiv) and Mrepo(r) is computed analogously to conferences via repository citation rate proxies. We set Ppre = 0.85 to prevent preprints from receiving inflated venue credit solely due to rapid diffusion, while still allowing highly cited preprints to contribute meaningfully through Cnorm (p).

Unified influence score. We combine paper-level and venue-level percentiles with fixed weights:

$$\mathcal { I } ( p ) = w _ { c } \cdot C _ { n o r m } ( p ) + w _ { v } \cdot V _ { n o r m } ( p ) , \quad w _ { c } = 0 . 6 , w _ { v } = 0 . 4 .$$

As in the main text, the higher weight on Cnorm mitigates venue "halo effects"" and preserves strong signals from influential papersin nichevenues or emerging areas.



--- Page Break ---



## D.5.3.EVIDENCESTATEMENT CREDIBILITYWEIGHTS

For each evidence statement ej (cluster G§), let P; be the set of unique witness papers that contributed at least one claim to that cluster.We define:

$$\text {Support} ( e _ { j } ) & = \sum _ { p \in P _ { j } } \mathcal { I } ( p ) , \quad \gamma _ { j } = \frac { \text {Support} ( e _ { j } ) } { \sum _ { i = 1 } ^ { k } \text {Support} ( e _ { i } ) } . \\$$

This paper-level de-duplication ensures that repeated mentions within the same witness do not artificially inflate support.

## D.6. Relation Classification, Weighted Voting, and Confidence Calibration

Given (i) the citing-side paraphrase cA and (i) a set of canonical evidence statements E = {e1, ..· , ek} with credibility weights {?i}, ICsV evaluates how each e; relates to cA and then aggregates via a reliability-aware vote.

## D.6.1.RELATIONCLASSIFICATIONPROMPT

```
weights: {'%}', ICSV evaluates how each e; relates to cA and then aggregates via a rebindy-aware value.

            D.6.1. RELATION CLASSIFICATION PROMPT

              System prompt: (relation classification).

            You are an expert scientific fact-checker.

            Inputs:
              (1) Claim c_A: what paper A attributes to paper B (a claim-preserving paragraph).
              (2) Evidence e_j: a canonical statement of what multiple other papers attribute to B
                      about one aspect.

            Task: decide the logical relation of e_j to c_A.
            Labels:
            - ENTAILS: e_j clearly supports c_A under the same scope/conditions.
            - CONTRACTDITS: e_j clearly conflicts with c_A (composite finding, incompatible scope,
              or mutually exclusive conditions).
            - NEUTRAL: e_j is about a different aspect, or is insufficient to judge c_A.

            Rules:
            - Be strict about scope and qualifiers. If scopes differ, prefer NEUTRAL unless
              the mismatch itself implies contradiction.
            - Do NOT assume untested details.
            Return JSON only.

            User prompt.
```

## User prompt.

```
Claim c_A (about paper B):
            {c_A}

            Evidence e_j (community-attributed statement about paper B):
            {e_j}

            Return JSON:
            {
```

We run relation classification with deterministic decoding (temperature O). To measure robustness, we additionally run a small self-consistency check (three independent decoding seeds at T = O; identical output is expected, but disagreements majority label.

We map labels to scalar votes v E {+1, 0, -1} for ENTAILS/NEUTRAL/CONTRADICTS.



--- Page Break ---



## D.6.2.WEIGHTED CONSENSUS SCORE

We compute the core consensus score as in the main text:

$$\mathcal { V } _ { \text {final} } = \sum _ { j = 1 } ^ { k } v _ { j } \cdot \gamma _ { j } \in [ - 1 , 1 ] ,$$

and apply thresholds Tsupport = 0.3 and Tmiscite = -0.3:

$$\ V e d i c t = \begin{cases} \text {Supported,} & \mathcal { V } _ { \text {final} } > 0 . 3 , \\ \text {Miscitation,} & \mathcal { V } _ { \text {final} } < - 0 . 3 , \\ \text {Undecidable,} & \text {otherwise.} \end{cases}$$

## D.6.3.CALIBRATED CONFIDENCE SCORE(ROBUSTUNDER DISAGREEMENT AND CONCENTRATION)

While |Vfinal| is a useful base signal, it can be misleading when (i) the committee is small, (ii) weights are dominated by a single witness cluster, or (i) evidence statements disagree. We therefore compute an adjusted confidence Conf E [O, 1] that is conservative under thesefailure modes.

Effectiveevidencesize.Weuse an effectivenumber ofevidencestatements(weight diversity):

$$n _ { e f f } = \frac { 1 } { \sum _ { j = 1 } ^ { k } \gamma _ { j } ^ { 2 } } ,$$

whichdecreaseswhen onecluster dominates.

Weighted disagreement. Let we = ≥j:R;=e  be the total credibility mass assigned to relation label l E {ENTAILS, NEUTRAL, CONTRADICTS}. Define normalized entropy:

$$H = - \frac { \sum _ { \ell } w _ { \ell } \log ( w _ { \ell } + \epsilon ) } { \log 3 } ,$$

with a small e for numerical stability. H increases with disagreement.

Stability factor.  Let a = &gt;§=1 Yja be the credibility-weighted relation stability under self-consistency.

Final confidence.We define:

$$C o n f = \underbrace { | \rangle _ { f i n a l } | \cdot \underbrace { \min \left ( 1 , \frac { n _ { e f f } } { K _ { \min } } \right ) } _ { m i g r a n i } \cdot } _ { \text {violation} } \underbrace { ( 1 - H ) } _ { \text {disagreement penalty} } \quad ^ { \cdot } \underbrace { \bar { a } } _ { \text {disagreement penalty} } \quad ^ { \cdot } .$$

This confidence is high only when the committee is sufficiently large/diverse, the evidence mass coheres, and relation labels are stable.

## D.7. Reliability-Aware Abstention and Diagnostic Reporting

ICSV is designed for high-stakes integrity workflows, where a false accusation is more harmful than an abstention. We therefore abstain whenever community evidence is not strong enough to support a traceable verdict.

Abstention triggers. ICSV returns UNDECIDABLE if any of the following holds:

- (i) Insufficient witnesses: |Copen| &lt; Kmin, with Kmin = 6.
- (ii)Low calibrated confidence:Conf&lt; 0.5(conservative default).
- (i) Low consensus margin: Vfinal E [Tmisite, Tsuppor] = [0.3, 0.3].
- (iv)High disagreement:H &gt; 0.6(evidence splits across entail/contradict/neutral).



--- Page Break ---



What abstention means (and what it does not).  An abstention is not a "failure" mode; it is an explicit integrity constraint. Under paywall conditions, deep semantic verification can be underdetermined. ICsV therefore refuses to overreach when the committee cannot reliably reconstruct B's contribution with sufficient consensus.

Auditable output bundle. For every verdict (including UNDECIDABLE), ICSV outputs:

- (1) cA and the final window radius used to stabilize it;
- (3) clusters {G}, evidence statements {e}, and their credibility weights {};
- (2) the witness set size|Copen|and each witness paper's Z(p);
- (4) per-cluster relation labels Rj, votes vj, and stability aj;
5. (5）Vfinal,verdict thresholds,and calibrated Conf with disagreement statistics.

This reporting makes each paywall decision traceable to specific community attributions and clearly communicates when evidenceis insufficient or contradictory.

## E. Evaluation Details: Grading, Decoding, and Token Accounting

## E.1. Acc-pass @3: Definition and Grading Pipeline

Candidate generation.For each miscitation instance and each evaluated method, we drawK =3independent samples from the underlying model by varying the random seed while keeping the decoding configuration fixed for that method. Each sample consists of: (i) a predicted validity label E {SUPPORTED, MISCITATION}, and (ii) a free-form natural-language explanation of the decision. Any explicit abstention (e.g., UNDECIDABLE) is treated as an ordinary label for grading purposes and will be marked incorrect whenever it disagrees with the gold label or fails to provide a faithful rationale.

Independent grader LLM.We use an independentgraderbased on gpt-4o-2024-08-06 to decide whether agiven sample is fully correct, jointly considering the label and the explanation. The grader sees the gold label and gold explanation together with a single model prediction and must output exactly one token: CORRECT or INCORRECT. The system and user prompts are:

## System prompt (grader).

Youareanexpertscientificeditor.

You will be given:

- 1.A gold label and gold explanation for a miscitation instance.
- 2.A model's predicted label and predicted explanation for the same instance.

Your taskis todecide whetherthe model's predictionis FULLYCORRECT.

Apredictionis FULLYCORRECT onlyif BOTHof the followinghold:

- :The predictedlabelexactlymatchesthegoldlabel.
- The predicted explanation identifies the same underlying error mechanism as the gold explanation (not just a generic restatement of the label).

Be strict.If the explanation is vague,only partially matches the gold rationale， introduces incorrect reasoning， or misses key aspects of the gold explanation, you must treat the prediction as INCORRECT.

Respond with a single token: either CORRECT or INCORRECT. Do not output any other text.

## User prompt (grader).

```
[ IN STANCE ]
```

Citing context:



--- Page Break ---



```
------------------------- AbiAgent Framework for Traceable Miscitation Detection in Scientific Literature -------------------------
        {CITING_TEXT}

        Gold label:
        {GOLD_LABEL}

        Gold explanation:
        {GOLD_EXPLANATION}

        [PREDICTION]
        Predicted label:
        {PRED_LABEL}

        Predicted explanation:
        {PRED_EXPLANATION}

        Respond with exactly one token:
        - CORRECT
        - INCORRECT

        For each instance and sample k \{ 1, 2, 3\}, the gradr returns a verdict g_{i} \{ CORRECT, INCORRECT\}.

        Metric definition.  Let N denote the number of evaluation instances for a given regime (MisciteBench-Open or
        MisciteBench-PaYall). Acc-pass@3 for a method is defined as:
```

Metric definition. Let N denote the number of evaluation instances for a given regime (MisciteBench-Open or MisciteBench-Paywall).Acc-pass@3for a method isdefined as:

$$A c { \text {-pass} } { \mathfrak { 3 } } = \frac { 1 } { N } \sum _ { i = 1 } ^ { N } 1 \left [ \exists k \leq 3 \text { such that } g _ { i k } = \text { CORRECT} \right ] ,$$

where 1[] is the indicator function. In words, an instance contributes 1 to the numerator if at least one of the three sampled predictions is graded as fully correct with respect to both the label and the explanation; otherwise it contributes O. Predictions graded as INCORRECT for any reason (wrong label, incomplete rationale, hallucinated rationale, or abstention) are not counted.

Human validation of the grader.To assess the reliability of the automatic grader, human experts manually inspected more than 3,0o0 randomly sampled grader decisions drawn across models, regimes, and label types. Disagreement between human judgment and the grader was observed in fewer than 0.5%of cases,predominantly on borderline instances where the strictness in these edge cases, as Acc-pass@3 is intended to measure diagnostically faithful explanations rather than loose paraphrases of thelabel.

## E.2.Decoding and SamplingSettings

Unless otherwise specified in the corresponding module appendix, we use the following decoding configurations:

Deterministic components. For single-step classification or scoring modules that should be deterministic, we use greedy used in ACSV Phase II, (i) the relation classification and other local decision steps inside ICSV where no self-consistency is applied, and (ii) lightweight utility calls such as format validation and consistency checks.

Self-consistency components. For modules that rely on multi-step reasoning and benefit from diversity, we use smallensemble self-consistency. Concretely, we sample M = 5 completions with temperature T = 0.7 and top-p = 0.95, and thenaggregatebymajorityvote:

- ·ACSVPhase IV (LRM deepreasoningfor ambiguous cases).
- Taxonomy-aligned miscitation classification (Section 3.4).



--- Page Break ---



If there is no strict majority, we fall back to the most frequent non-abstaining class; when the distribution is too diffuse or inconsistent, the module may emit an explicit UNDECIDABLE label, which is treated as incorrect under Acc-pass@3.

Baseline prompts.For the Full-Text and Search baselines,we use a mildly stochastic but low-variance configuration: temperature T = 0.2 with the provider's default top-p and other decoding parameters. This allows limited exploration across the K = 3 samples while keeping predictions reasonably stable for grading.

Averaging across runs.To reduce variance from global random seeds and any stochasticity in external services (e.g., web search for the Search baselines), we repeat each full evaluation three times with different random seeds. All reported numbers in the main text and appendix tables are the arithmetic mean over these three runs.

## E.3.TokenAccountingandTokenEconomy

Per-instance token counting. For every method and evaluation instance, we record the total number of tokens consumed by the verification pipeline, including both inputs and outputs, and including all internal calls (retrieval, NLI, committee reasoning, taxonomy classification,etc.). Concretely,for each model call we log: (i) the number of input tokens, (ii) the number of output tokens, and sum these over all calls involved in processing that instance.We use the official tokenization for each provider (e.g., the same tokenizer used for billing) to avoid discrepancies between counted and billed tokens.

Token Economy definition. For a given backbone model, let TokrT denote the mean number of tokens per instance for the Full-Text baseline, and let TokBiBAGENT denote the mean number for BIBAGENT (specifically, ACSV in MisciteBench-Open) evaluated on the same set of instances.We define TokenEconomy as

$$T o k _ { E } e c \, = \, 1 - \frac { T o k _ { B i B A G ENT } } { T o k _ { F T } } ,$$

which can be interpreted as the fraction of tokens saved by BIBAGENT relative to the Full-Text baseline for that backbone. A value of TokenEcon = 0.794,for example, means that B1BAGENT uses 79.4% fewer tokens on average than the corresponding Full-Text setup.

To make this comparison meaningful, Token Economy is computed only on the subset of instances for which both methods return a non-abstaining verdict (i.e.,they emit a concrete SUPPORTED or MISCITATION label).Instances on which onemethod abstains andtheother does notareexcludedfromthetoken-economy calculationbut are stillincluded in Acc-pass@3with abstentionstreated asincorrectpredictions.

## F.EvidenceCommitteeReliabilityAblation

ICSV(Appendix D) is only useful in the paywalled regime if its Evidence Committeebehaves in a predictable, conservatively calibrated way: when community evidence is rich, it should speak with high confidence and high precision; when evidence is thin or inconsistent, it should abstain rather than speculate. The main paper states that we observe a sharp reliability transition once an aspect of the paywalled source is supported by at least six independent witnesses. This appendix provides the quantitative ablation that underpins that claim and justifies the global committee-size threshold used by ICsV's reliability-aware abstention rule.

## F.1.Protocol

For a paywalled source B, ICSV groups all downstream open-access citers into semantic clusters G1, ... , Gk, where each Grepresents one coherent aspect of what the community attributes toB (method,dataset,empirical finding,etc.). Let P denote the set of distinct witness papers whose claims end up in G§, and

$$n _ { j } = | P _ { j } |$$

thenumber ofindependent committeevoters for that aspect.From each cluster we distill an evidence statemente;with credibility weight j (AppendixD),and define the dominant aspect for the citation as

$$j ^ { * } = \arg \max _ { j } \gamma _ { j } , \quad e ^ { * } = e _ { j ^ { * } } .$$



--- Page Break ---



Figure 2. Evidence Committee behavior as a function of the number of distinct witness papers Nvoter supporting the dominant evidence statement e*for a paywalled citation.Curves show non-abstention rate,conditional accuracy, and mean calibrated confidence(AppendixD);shadedbandsindicatevariation acrossbackbones.Thesharp andstable transition aroundNvoter =6motivates the choice Kmin=6inICsV's reliability-aware abstention rule.

<!-- image -->

Our ablationfocuses on

$$n _ { v o t e r } = n _ { j ^ { * } } ,$$

the number of distinct witness papers that support the aspect of B which most strongly drives ICsV's verdict on that citation.

We run the unmodified ICsV pipeline on the full MisciteBench-Paywall split. For every paywalled citation that admits at leastonenon-emptycluster,andforeachbackbone,werecord:

- the final verdict (Supported, Miscitation, or Undecidable);
- ·whethertheverdictiscorrectunderthebenchmarklabel;
- the calibrated confidence score Conf E [O, 1] from Appendix D, which combines the consensus margin |Vinal, effective committee size,label disagreement, and self-consistency stability.

We then bucket citations by the integer value of Nvoter in the range 1 ≤ Nvoter ≤ 25. For each bucket c, and for each backbone, wecompute:

1. the non-abstention rate: the fraction of citations with Nvoter = c on which ICsV outputs Supported or Miscitation rather thanUndecidable;
2. the conditional accuracy: the fraction of those non-abstaining verdicts that match the ground truth;
3. the mean calibrated confidence E[Conf | Nvoter = c].

The curves in Figure 2 plot these quantities after averaging over backbones; shaded bands indicate the range across backbones. All hyperparameters and thresholds are identical to those used in the main experiments; we do not re-tune ICsV for this study.



--- Page Break ---



## F.2. Quantitative Trends

Threeregimes emerge consistently acrossmodels and disciplines.

Single or few witnesses (nvoter ≤ 2).When the dominant aspect of B is supported by only one or two downstream papers, ICsV behaves cautiously. Non-abstention rates are low, and the system frequently returns Undecidable because the consensus margin and effective committee size termsin Conf are small.Among thefew cases whereICsV does commit, conditional accuracy is noticeably weaker and confidence scores cluster in a moderate band. In this regime, individual witness papers often describeBinidiosyncratic or overly generic ways, and a single outlier can heavily influence the vote. The abstention mechanism therefore activates often,which is precisely the desired behavior for a conservative verifier operatingundersparsecommunityevidence.

Small committees (3 ≤ Mvoter ≤ 5).  As Mvoter grows into the range of three to five independent witnesses, non-abstention rates and conditional accuracyboth improve:thecommittee has enough redundancy tofilter out extreme outliers and resolve many straightforward paywalled cases.However,the curves in Figure 2 stillexhibit noticeablevariability across buckets in this regime. The calibrated confidence Conf rises compared to the Nvoter ≤ 2 regime, but remains in an intermediate range, reflecting two residual sources of uncertainty: (i) disagreement between clusters about the precise scope of B's contribution, and (i) moderate label entropy when witness papers emphasize different aspects of B or mix descriptive and evaluative citations. In practice, ICsV continues to abstain on a substantial fraction of citations here, and the system remains deliberately conservative.

distinct witness papers. Beyond this point, all three metrics undergo a clear and stable shift:

- on the majority of paywalled citations in these buckets,because both the consensus margin and the effective committee
- Conditional accuracy of non-abstaining verdicts increases and stabilizes at a high level. Across backbones, once six yield only marginal gains.
- The mean calibrated confidence E[Conf | Nvoter = c] crosses O.8 and remains in a high-confidence band for all c ≥ 6. In other words, whenever a paywalled aspect is supported by six or more independent witnesses, ICsV not only decidesmore often,but does so with confidence scores that reflect genuinely strong and internally coherent community evidence.

Importantly,this transition is not an artifact of a particularbackbone orfield.The same qualitativekneein the curves appears when the ablation is recomputed separately for each backbone and for coarse discipline groups (e.g., Clinical Medicine vs. witnesses for the dominant aspect—-is remarkably stable.

## F.3.ChoiceofThreshold andRobustness

The global threshold Kmin = 6 used by ICsV's reliability-aware abstention rule is therefore not a hand-tuned hyperparameter, but the empirical knee point of a three-way trade-off:

- ·Below six witnesses, the Evidence Committee is too small to be trustworthy: non-abstention rates are lower, conditional accuracy is noticeably weaker, and the calibrated confidence Conf correctly reflects this by staying in a cautious range. Allowing aggressive decisions here would yield an undesirable increase in false accusations under genuine information scarcity.
- ·At six witnesses,the curves in Figure 2 enter a stable high-precision regime.Both the committee size and the consensus structure are sufficient for ICsV to exploit the community's distributed memory of the paywalled source, and the confidence calibration in Appendix D rewards this with high Conf values.



--- Page Break ---



- Raising Kmin beyond six would sacrifice coverage for little additional precision. While larger committees remain slightly more stable, the incremental gain is small compared to the loss in the number of paywalled citations that can be decided at all, especially in niche subfields where only a handful of downstream citers exist.

We further stress-test this choice by recomputing the ablation under several perturbations: varying the confidence threshold used to declare a verdict vs. abstention, subsampling the witness set, and repeating the analysis on random halves of MisciteBench-Paywall. In all cases,the location of the knee in the reliability curves remains close to six witnesses, even though the absolute values of the metrics shift slightly. This robustness suggests that Kmin = 6 captures a property of the underlying citation graph—when the literature around a paywalled source is broad and coherent enough to support stable reconstruction—-rather than an artifact of a particular model or parameter setting.

Taken together, these results substantiate the design of ICsV's Evidence Committee.The system only"speaks with conviction"about paywalled sources when the dominant aspect is backed by a sufficientlylarge and internally consistent community of citers,and it is willing to abstain explicitly when that condition is not met. This calibrated behavior is essential for deploying BIBAGENT in high-stakes editorial and auditing workflows: it ensures that paywall robustness is grounded in measurablecommunityredundancyrather thanin unexaminedmodelconfidence.