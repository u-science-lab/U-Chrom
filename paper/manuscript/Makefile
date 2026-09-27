.PHONY: all clean fig1 fig2 figures

all: main.pdf

main.pdf: main.tex refs.bib captions/*.tex figures/*.pdf
	latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex

# Copy the final Figure 1 from paper/fig1.
fig1:
	cp ../fig1/fig1_final.pdf figures/fig1.pdf

# Copy the final Figure 2 from paper/fig2 (re-draw it with `python ../fig2/make_fig2.py` first).
fig2:
	cp ../fig2/fig2.pdf figures/fig2.pdf

figures: fig1 fig2

clean:
	latexmk -C
