REPORT_DIR := report_source
REPORT_TEX := $(REPORT_DIR)/main.tex
REPORT_PDF := report.pdf
REPORT_BUILD_PDF := $(REPORT_DIR)/main.pdf
LATEX := pdflatex
LATEX_FLAGS := -interaction=nonstopmode -halt-on-error

.PHONY: all report clean distclean

all: report

report: $(REPORT_PDF)

$(REPORT_PDF): $(REPORT_TEX)
	cd $(REPORT_DIR) && $(LATEX) $(LATEX_FLAGS) main.tex
	cd $(REPORT_DIR) && $(LATEX) $(LATEX_FLAGS) main.tex
	mv -f $(REPORT_BUILD_PDF) $(REPORT_PDF)

clean:
	rm -f $(REPORT_DIR)/*.aux \
		$(REPORT_DIR)/*.log \
		$(REPORT_DIR)/*.out \
		$(REPORT_DIR)/*.toc \
		$(REPORT_DIR)/*.lof \
		$(REPORT_DIR)/*.lot \
		$(REPORT_DIR)/*.fls \
		$(REPORT_DIR)/*.fdb_latexmk \
		$(REPORT_DIR)/*.synctex.gz \
		$(REPORT_DIR)/*.bbl \
		$(REPORT_DIR)/*.blg

distclean: clean
	rm -f $(REPORT_PDF)
