"""Known cases from calibrating against real City Tech data (Oct 2026). If you change the
AI rules, these tell you whether you re-introduced an old false positive."""
import citytech_pubs as C


def ai(title, abstract="", keywords="", topics=()):
    return C.classify_ai({"title": title, "abstract": abstract, "keywords": keywords,
                          "topics": [{"name": n, "subfield": s, "score": sc} for n, s, sc in topics]})[0]


def test_title_terms_count():
    assert ai("Can We Discover Physical Models Using Machine Learning?")
    assert ai("Council of LLMs: Evaluating Large Language Models")
    assert ai("AI Method for Classification of Breast Lesion Images")


def test_quantum_and_crypto_topics_are_not_ai():
    # OpenAlex files these under its "Artificial Intelligence" subfield
    assert not ai("Quantum entanglement for two qubits", topics=[("Quantum Information and Cryptography", "Artificial Intelligence", .9)])
    assert not ai("Rédei permutations with cycles", topics=[("Coding theory and cryptography", "Artificial Intelligence", .9)])


def test_robotics_courses_are_not_ai_research():
    assert not ai("Development of a Raspberry PI-Controlled VEX Robot for a Robotics Course",
                  topics=[("Educational Robotics and Engineering", "Artificial Intelligence", .9)])


def test_cnn_news_and_ai_lowercase_words():
    assert not ai("Captivity Narratives Then and Now", abstract="as reported by CNN in 2019")
    assert not ai("Financial aid and student outcomes")


def test_deep_learning_as_pedagogy_is_not_ai():
    assert not ai("Place-Based Learning as a High Impact Educational Practice",
                  abstract="deep learning for students in classrooms")


def test_single_passing_mention_in_abstract_is_not_enough():
    assert not ai("Star Wars at Fifty", abstract="the film imagines artificial intelligence")
    assert ai("Ocean carbon reconstructions", abstract="we train machine learning models such as random forests")


def test_ai_topic_names_count():
    assert ai("Efficient models for edge devices", topics=[("Advanced Neural Network Applications", "Artificial Intelligence", .8)])


def test_words_inside_other_words_dont_count():
    # found on the first GitHub run (2026-10-26)
    assert not ai("Synthesis and molecular docking of caffeic acid analogues",
                  topics=[("Cholinesterase and Neurodegenerative Diseases", "Pharmacology", .9)])
    assert not ai("Diversity-dependent cladogenesis throughout western Mexico",
                  topics=[("Evolution and Paleontology Studies", "Paleontology", .9)])
    assert not ai("Frailty in older adults", topics=[("Aging and Gerontology Research", "Gerontology", .9)])


def test_robot_hardware_is_not_ai():
    assert not ai("Dynamic self-assembly of magnetic micro-swimmers", topics=[("Micro and Nano Robotics", "Biomedical Engineering", .9)])
    assert not ai("A pneumatic gripper", topics=[("Soft Robotics and Applications", "Control and Systems Engineering", .9)])
    assert ai("Path planning for warehouse robots", topics=[("Robotic Path Planning Algorithms", "Artificial Intelligence", .9)])


def test_same_phrase_twice_is_one_weak_signal():
    assert not ai("Star Wars at Fifty", keywords="artificial intelligence", abstract="the film imagines artificial intelligence")
    assert not ai("Global Finance", keywords="multi-agent", abstract="a multi-agent view of markets")
