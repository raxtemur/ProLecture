TEX  := $(HOME)/.TinyTeX/bin/x86_64-linux
NAME := prolecture

# xelatex rather than pdflatex: the text is set in the system DejaVu Sans via
# fontspec, which keeps the font stack the same as when the slides were Cyrillic
all: $(NAME).pdf

$(NAME).pdf: $(NAME).tex
	PATH=$(TEX):$$PATH xelatex -interaction=nonstopmode $(NAME).tex
	PATH=$(TEX):$$PATH xelatex -interaction=nonstopmode $(NAME).tex

# page images — to eyeball the layout without opening a viewer
png: $(NAME).pdf
	pdftoppm -r 110 -png $(NAME).pdf page

clean:
	rm -f $(NAME).aux $(NAME).log $(NAME).nav $(NAME).out $(NAME).snm \
	      $(NAME).toc page-*.png

.PHONY: all png clean
