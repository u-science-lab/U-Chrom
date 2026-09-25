.PHONY: all clean fig1

all: main.pdf

main.pdf: main.tex refs.bib captions/*.tex figures/*.pdf
	latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex

# Copy the final Figure 1 from paper/fig1.
fig1:
	cp ../fig1/fig1_final.pdf figures/fig1.pdf

clean:
	latexmk -C
