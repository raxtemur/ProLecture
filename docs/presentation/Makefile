TEX  := $(HOME)/.TinyTeX/bin/x86_64-linux
NAME := prolecture

# xelatex, а не pdflatex: кириллица берётся системным шрифтом DejaVu Sans
# через fontspec, иначе пришлось бы тащить cm-super и T2A-кодировку
all: $(NAME).pdf

$(NAME).pdf: $(NAME).tex
	PATH=$(TEX):$$PATH xelatex -interaction=nonstopmode $(NAME).tex
	PATH=$(TEX):$$PATH xelatex -interaction=nonstopmode $(NAME).tex

# картинки страниц — глазами смотреть вёрстку, не открывая просмотрщик
png: $(NAME).pdf
	pdftoppm -r 110 -png $(NAME).pdf page

clean:
	rm -f $(NAME).aux $(NAME).log $(NAME).nav $(NAME).out $(NAME).snm \
	      $(NAME).toc page-*.png

.PHONY: all png clean
