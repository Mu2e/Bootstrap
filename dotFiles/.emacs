
;
; this will help emacs understand formatting of fcl files
; git clone https://github.com/knoepfel/art-fhicl.git
; and save the ".el" file somewhere in your area
;
; then add the following to your .emacs (with fixed path)
;
; (load "/path/to/art-fhicl-mode.el" nil t t)
; (add-to-list 'auto-mode-alist '("\\.fcl\\'" . art-fhicl-mode))
;
; See also the wiki
; https://mu2ewiki.fnal.gov/wiki/Editors

; here is away to get clang-format to run on a buffer with key "<crtl><alt> f"
;  
;  (add-to-list 'exec-path "/cvmfs/mu2e.opensciencegrid.org/artexternals/clang/v5_0_1/Linux64bit+3.10-2.17/bin")
;  (load "/cvmfs/mu2e.opensciencegrid.org/artexternals/clang/v5_0_1/Linux64bit+3.10-2.17/share/clang/clang-format.el")
;  (setq-default clang-format-style "google")
;  (global-set-key "\C-\M-f" 'clang-format-buffer )
;  

; highlight tabs and trailing whitespace
; turn off tabs in c++ and a few other modes
(require 'whitespace)
(setq whitespace-style '(face empty tabs trailing))
(add-hook 'c++-mode-hook
            '(lambda ()
                    (whitespace-mode)))
(add-hook 'c++-mode-hook
          '(lambda ()
             (setq indent-tabs-mode nil)))
(add-hook 'sh-mode-hook
            '(lambda ()
                    (whitespace-mode)))
(add-hook 'sh-mode-hook
          '(lambda ()
             (setq indent-tabs-mode nil)))
(add-hook 'python-mode-hook
            '(lambda ()
                    (whitespace-mode)))
(add-hook 'python-mode-hook
          '(lambda ()
             (setq indent-tabs-mode nil)))
(add-hook 'perl-mode-hook
            '(lambda ()
                    (whitespace-mode)))
(add-hook 'perl-mode-hook
          '(lambda ()
             (setq indent-tabs-mode nil)))
(add-hook 'latex-mode-hook
            '(lambda ()
                    (whitespace-mode)))
(add-hook 'latex-mode-hook
          '(lambda ()
             (setq indent-tabs-mode nil)))

;
; always add a newline at the end of files
;
(setq-default require-final-newline t)

;
; this verion just prompts you for newline
;
;(setq-default require-final-newline 'visit-save)
