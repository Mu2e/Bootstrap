" use 2-space soft tabs.  Some of these may be redundant
:set softtabstop=2
:set shiftwidth=2
:set tabstop=2
:set expandtab
" turn on cursor column and row listing
:set ruler
" configure window status info
:set statusline=%<%F\ %n%h%m%r%=%-14.(%l,%c%V%)\ %P
:set laststatus=2
" configure spellcheck, but turn it off by default: enable with ':set spell'
:setlocal spell spelllang=en_us
:set spellfile=~/.vim.myspell.add
:set nospell
" configure display of hidden characters: these can be modfied as desired, or
" turned off with ':set listchars='
:set listchars=eol:$,tab:>-,trail:~,extends:>,precedes:<
:set list
" don't distract open menu with 'hidden' files
:let g:netrw_list_hide= '.*\.swp$,*\.os$,*\.C_d'
" highlght search hits
:hi Search term=reverse ctermbg=7
" Tell vim where to look for #include files
:set path =.,Offline,Production,$MUSE_BUILD_BASE,,
" enable syntax color highlighting (language specific)
:syntax enable
:" use latex for tex
:let g:tex_flavor = "latex"
" c++
au BufNewFile,BufRead *.cpp,*.cc,*.C set syntax=cpp
" use perl mode for fcl files; this gets the syntax highlighting and brace matching correct
:au BufNewFile,BufRead *.fcl,*.fhicl set syntax=perl
" check whitespice on exit
:autocmd BufWritePre * :%s/\s\+$//e
" let Vim auto-indent by filetype
:set autoindent
:set smartindent
filetype plugin indent on

