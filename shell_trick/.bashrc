# my prefered fast shell trick

# some more ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'


# for git
alias gs='git status'
alias gc='git checkout'
alias gd='git diff'
alias gname='git config --global user.name'
alias gmail='git config  --global user.email'
alias mail-ssh-key='ssh-keygen -t rsa -C'

# for rsync
alias r='rsync -avqP'

# for quick compress
function qc() {
    if [ -n "$1" ] ; then
        FILE=$1
        case $FILE in
        *.tar) shift && tar -cf $FILE $* ;;
        *.tar.bz2) shift && tar -cjf $FILE $* ;;
        *.tar.xz) shift && tar -cJf $FILE $* ;;
        *.tar.gz) shift && tar -czf $FILE $* ;;
        *.tgz) shift && tar -czf $FILE $* ;;
        *.zip) shift && zip $FILE $* ;;
        *.rar) shift && rar $FILE $* ;;
        esac
    else
        echo "usage: q-compress <foo.tar.gz> ./foo ./bar"
    fi
}

function qe() {
    if [ -f $1 ] ; then
        case $1 in
        *.tar.bz2)   tar -xvjf $1    ;;
        *.tar.gz)    tar -xvzf $1    ;;
        *.tar.xz)    tar -xvJf $1    ;;
        *.bz2)       bunzip2 $1     ;;
        *.rar)       rar x $1       ;;
        *.gz)        gunzip $1      ;;
        *.tar)       tar -xvf $1     ;;
        *.tbz2)      tar -xvjf $1    ;;
        *.tgz)       tar -xvzf $1    ;;
        *.zip)       unzip $1       ;;
        *.Z)         uncompress $1  ;;
        *.7z)        7z x $1        ;;
        *)           echo "don't know how to extract '$1'..." ;;
        esac
    else
        echo "'$1' is not a valid file!"
    fi
}

# for testing memory perf
alias mem_perf='dd if=/dev/zero of=/dev/null bs=1M count=32768'

# for timer
alias timer='while sleep 1;do tput sc;tput cup 0 $(($(tput cols)-29));date;tput rc;done&'

# for ascii
asc = 'man ascii'

##############################################################################
# 快速跳转 - https://github.com/rupa/z
##############################################################################

#source /path/to/z.sh               # .bashrc 中初始化 z.sh
#z                                  # 列出所有历史路径以及他们的权重
#z foo                              # 跳到历史路径中匹配 foo 的权重最大的目录
#z foo bar                          # 跳到历史路径中匹配 foo 和 bar 权重最大的目录
#z -l foo                           # 列出所有历史路径中匹配 foo 的目录及权重
#z -r foo                           # 按照最高访问次数优先进行匹配跳转
#z -t foo                           # 按照最近访问优先进行匹配跳转