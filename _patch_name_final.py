import io

P = r"D:\Vento_atag_timer_fixed_final\Vento\profile_analyzer\name_analyzer.py"
t = io.open(P, encoding="utf-8").read()

START = "    def analyze(self, first_name: Optional[str]) -> AnalyzerResult:"
# analyze() dan keyingi birinchi top-level bo'lmagan def gacha (keyingi metod)
i = t.index(START)
# keyingi metodni topamiz (\n    def ) — analyze dan keyingi
nxt = t.index("\n    def ", i + len(START))
head_doc_end = t.index('"""', i + len(START)) + 3
head = t[i:head_doc_end]

new_body = head + '''
        normalized_name = self.normalize_name(first_name)

        if not normalized_name:
            return AnalyzerResult(
                signal=0,
                analyzer_name="name",
                details={"reason": "empty_or_invalid_name"}
            )

        # ML MODEL — asosiy qaror (sklearn klassifikator, ehtimollik bilan)
        try:
            ml_model = self._get_ml_model()
            if ml_model is not None:
                first_w = normalized_name.split()[0]
                ml_prob = ml_model.predict_female_prob(first_w)
                if ml_prob >= float(getattr(ml_model, "threshold", 0.60)):
                    rule_hit, rule_method, rule_info = self._rule_match(first_w)
                    return AnalyzerResult(
                        signal=1,
                        analyzer_name="name",
                        details={
                            "name": first_w,
                            "method": "ml_classifier",
                            "ml_female_prob": round(ml_prob, 3),
                            "rule_match": rule_hit,
                            "rule_method": rule_method,
                            "rule_info": rule_info,
                        }
                    )
        except Exception as e:
            logger.debug("ML name inferens xatosi: %s", e)

        # Eski qoida-bazasi (ML past bo'lsa yoki yo'q bo'lsa — kompatibilitet)
'''

# Eski analyze tanasi ichidagi birinchi "Extract first word" dan keyingi qismni qoldiramiz
tail_marker = "# Extract first word (handle multi-word names)"
tail_i = t.index(tail_marker, i)
old_len = len(t[i:nxt])
new_t = t[:i] + new_body + "\n        " + t[tail_i:]
io.open(P, "w", encoding="utf-8").write(new_t)
print("OK: analyze qayta yozildi, eski tanasidan olib tashlandi:", old_len, "belgi")
