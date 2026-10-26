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
