.PHONY: all supp clean fig1 fig2 figS1 figures tables

all: main.pdf

supp: supplement.pdf

main.pdf: main.tex refs.bib captions/*.tex figures/*.pdf supp/*.tex
	latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex

supplement.pdf: supplement.tex refs.bib captions/figS1.tex supp/*.tex figures/figS1.pdf
	latexmk -xelatex -interaction=nonstopmode -halt-on-error supplement.tex

# Copy the final Figure 1 from paper/fig1.
fig1:
	cp ../fig1/fig1_final.pdf figures/fig1.pdf

# Copy the final Figure 2 from paper/fig2 (re-draw it with `python ../fig2/make_fig2.py` first).
fig2:
	cp ../fig2/fig2.pdf figures/fig2.pdf

# Supplementary Fig. S1 (re-draw it with `python ../fig2/make_figS_fig2.py` first).
figS1:
	cp ../fig2/figS_fig2.pdf figures/figS1.pdf

figures: fig1 fig2 figS1

# Supplementary Table S1 bodies (supp/tableS1_*.tex) from the generated evidence table.
tables:
	python make_tableS1.py ../fig2/tableS_capabilities.md supp

clean:
	latexmk -C main.tex
	latexmk -C supplement.tex
