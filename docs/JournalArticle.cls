%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%                                                                              %
%                        LaTeX Journal Article Template                        %
%                                 LaTeX Class                                  %
%                                                                              %
%                                   Author:                                    %
%                                Koen Reinders                                 %
%                           koenf.reinders@gmail.com                           %
%                                                                              %
%                                   License:                                   %
%                               CC-BY-NC-SA 4.0                                %
%              https://creativecommons.org/licenses/by-nc-sa/4.0/              %
%                                                                              %
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%-------------------------------------------------------------------------------
%   CLASS CONFIGURATION
%-------------------------------------------------------------------------------

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{JournalArticle}[02/06/2025]

\usepackage{etoolbox} % Required for conveniently changing commands

% Pass through any options specified to the base class
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax % Process class options
\LoadClass{article} % Load base class
\usepackage{ifluatex} % Provides switch so we include LuaTex compatibility

%-------------------------------------------------------------------------------
%   DOCUMENT STRUCTURE AND FORMATTING
%-------------------------------------------------------------------------------

% Paragraph formatting
\setlength{\parindent}{0pt}
\setlength{\parskip}{1\baselineskip plus 0.1pt}

% Page margins
\usepackage[
    top=2.5cm,
    bottom=2.5cm,
    left=2cm,
    right=2cm,
    footskip=1cm,
    columnsep=20pt,
]{geometry}

% Font settings
\usepackage{microtype} % Improve text spacing
\linespread{1.05} % Slightly increase line spacing

\ifluatex
    \usepackage{fontspec} % LuaTeX uses fontspec for font settings
    \setmainfont{Libertinus Serif} % Use Libertinus font
\else
    \usepackage[T1]{fontenc} % pdflatex uses fontenc
    \usepackage{libertinus} % Use Libertinus font
\fi

%-------------------------------------------------------------------------------
%   HEADERS AND FOOTERS
%-------------------------------------------------------------------------------

\usepackage{fancyhdr} % For customizing page headers and footers

\pagestyle{fancy} % Enable the use of custom headers and footers
\fancyhf{} % Clear default settings
\setlength{\headheight}{14pt} % Slightly increase header height

% Header and footer content
\fancyhead[LE,RO]{\leftmark} % Show section name instead of subsection
\fancyfoot[LO,RE]{\thepage}

%-------------------------------------------------------------------------------
%   SECTION FORMATTING
%-------------------------------------------------------------------------------

\usepackage{titlesec} % Required for modifying sections

% Section formatting
\titleformat%
    {\section} % Section type to modify
    [block] % Layout type
    {\Large\bfseries} % Label and title formatting
    {\thesection} % Section label
    {0.5em} % Horizontal spacing between section label and title
    {} % Code before section title
    [] % Code after section title
    
\titleformat%
    {\subsection} % Section type to modify
    [block] % Layout type
    {\raggedright\large\bfseries} % Label and title formatting
    {\thesubsection} % Section label
    {0.5em} % Horizontal spacing between section label and title
    {} % Code before section title
    [] % Code after section title

\titleformat%
    {\subsubsection} % Section type to modify
    [block] % Layout type
    {\bfseries} % Label and title formatting
    {} % Section label
    {0.5em} % Horizontal spacing between section label and title
    {} % Code before section title
    [] % Code after section title

% Section spacing
\titlespacing*{\section}
  {0pt}   % left margin
  {1.5ex plus 1ex minus .2ex}   % space before
  {0.8ex plus .2ex}   % space after

\titlespacing*{\subsection}
  {0pt}
  {1.25ex plus 0.8ex minus .2ex}
  {0.6ex plus .2ex}

\titlespacing*{\subsubsection}
  {0pt}
  {1ex plus 0.5ex minus .2ex}
  {0.4ex plus .2ex}
 

%-------------------------------------------------------------------------------
%   BIBLIOGRAPHY
%-------------------------------------------------------------------------------

\usepackage[
    backend=biber,
    citestyle=nature,
    bibstyle=nature,
    sorting=none,
    natbib=true,
    url=true,
    doi=true,
]{biblatex}

\addbibresource{references.bib} % BibLaTeX bibliography file
\let\cite=\supercite % Redefine cite for supercite style in-text citations

% Add brackets around citation numbers. Credit goes to Marco Daniel
% https://tex.stackexchange.com/questions/114987/biblatex-supercite-with-square-
% brackets-and-grouped
\DeclareCiteCommand{\supercite}[\mkbibsuperscript]
  {\usebibmacro{cite:init}%
   \let\multicitedelim=\supercitedelim
   \iffieldundef{prenote}
     {}
     {\BibliographyWarning{Ignoring prenote argument}}%
   \iffieldundef{postnote}
     {}
     {\BibliographyWarning{Ignoring postnote argument}}%
  \bibopenbracket}%
  {\usebibmacro{citeindex}%
   \usebibmacro{cite:comp}}
  {}
  {\usebibmacro{cite:dump}\bibclosebracket}

%-------------------------------------------------------------------------------
%   TABLES AND CAPTIONS
%-------------------------------------------------------------------------------

\usepackage{booktabs} % Better horizontal rules in tables
\usepackage{array} % Required for manipulating table columns
\usepackage{multirow} % Allows table cells that span more than one row
\usepackage{caption} % Customizing captions
\usepackage{subcaption} % Customizing subcaptions

%-------------------------------------------------------------------------------
%   LINK FORMATTING
%-------------------------------------------------------------------------------

\PassOptionsToPackage{hyphens}{url} % Allow line breaks at hyphens in URLs and DOIs
\usepackage[
    pdfencoding=unicode,
    psdextra,
    bookmarks=true,
]{hyperref}

% Set colors for links
\hypersetup{
    breaklinks = true,
    colorlinks = true,
    linkcolor = blue,
    urlcolor = blue,
    citecolor = blue,
    filecolor = black
}

% Change url text type from the default \texttt to normal
\urlstyle{same}

%-------------------------------------------------------------------------------
%   SVG IMAGE SUPPORT
%-------------------------------------------------------------------------------

% Enable support for SVG images, converting them to PDF for LaTeX compatibility.  
% Ensure compatibility with LuaTeX by aliasing pdfTeX commands if LuaTeX is used.  
\ifluatex
    \usepackage{pdftexcmds}
    \makeatletter
    \let\pdfstrcmp\pdf@strcmp
    \let\pdffilemoddate\pdf@filemoddate
    \makeatother
\fi
\usepackage{svg}

%-------------------------------------------------------------------------------
%   MATH AND SCIENTIFIC NOTATION
%-------------------------------------------------------------------------------

\usepackage{mathtools} % Also loads amsmath
\usepackage{amssymb} % More math symbols
\usepackage{siunitx} % Formatting quantities and SI units
\numberwithin{equation}{section} % Number equations based on section numbers
\usepackage[capitalize]{cleveref} % Easier cross-referencing

%-------------------------------------------------------------------------------
%   ADDITIONAL PACKAGES
%-------------------------------------------------------------------------------

\usepackage{csquotes}
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{float}
\usepackage{typed-checklist}
\usepackage{tabulary}
\usepackage{listings}
\usepackage{forest}

%-------------------------------------------------------------------------------
%   TEXT ADJUSTMENTS
%-------------------------------------------------------------------------------

%\emergencystretch=\maxdimen
%\hyphenpenalty=10000
%\hbadness=10000

%-------------------------------------------------------------------------------
%   MACROS
%-------------------------------------------------------------------------------

\newcommand{\citationneeded}{\textsuperscript{\color{red} [citation needed]}}
\newcommand{\rednote}[1]{{\color{red} [#1]}}
