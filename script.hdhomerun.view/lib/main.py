# -*- coding: utf-8 -*-
import time
import xbmc, xbmcgui

import hdhr
import kodigui
import util
import player
import skin

MAX_TIME_INT = 31536000000 #1000 years from Epoch

CHANNEL_DISPLAY = u'[COLOR FF99CCFF]{0}[/COLOR] {1}'

class BaseWindow(xbmcgui.WindowXML):
    def __init__(self,*args,**kwargs):
        self._closing = False
        self._winID = ''

    def onInit(self):
        self._winID = xbmcgui.getCurrentWindowId()

    def setProperty(self,key,value):
        if self._closing: return
        xbmcgui.Window(self._winID).setProperty(key,value)
        xbmcgui.WindowXMLDialog.setProperty(self,key,value)

    def doClose(self):
        self._closing = True
        self.close()

    def onClosed(self): pass

class BaseDialog(xbmcgui.WindowXMLDialog):
    def __init__(self,*args,**kwargs):
        self._closing = False
        self._winID = ''

    def onInit(self):
        self._winID = xbmcgui.getCurrentWindowDialogId()

    def setProperty(self,key,value):
        if self._closing: return
        xbmcgui.Window(self._winID).setProperty(key,value)
        xbmcgui.WindowXMLDialog.setProperty(self,key,value)

    def doClose(self):
        self._closing = True
        self.close()

    def onClosed(self): pass

class KodiChannelEntry(BaseDialog):
    def __init__(self,*args,**kwargs):
        self.digits = str(kwargs['digit'])
        self.hasSubChannels = kwargs.get('has_sub_channels',False)
        self.channel = ''
        self.set = False
        BaseDialog.__init__(self,*args,**kwargs)

    def onInit(self):
        BaseDialog.onInit(self)
        self.showChannel()

    def onAction(self,action):
        try:
            if action.getId() >= xbmcgui.REMOTE_0 and action.getId() <= xbmcgui.REMOTE_9:
                digit = str(action.getId() - 58)
                self.digits += digit
                if '.' in self.digits:
                    if len(self.digits.split('.',1)[-1]) > 1: #This can happen if you hit two keys at the same time
                        self.digits = self.digits[:-1]
                    self.showChannel()
                    return self.submit()

                if len(self.digits) < 5:
                    return self.showChannel()

                self.digits = self.digits[:-1]

            elif action == xbmcgui.ACTION_NAV_BACK:
                return self.backspace()
            elif action == xbmcgui.ACTION_SELECT_ITEM:
                if not self.hasSubChannels or not self.addDecimal():
                    return self.submit()
        except:
            util.ERROR()
            BaseDialog.onAction(self,action)
            return

        BaseDialog.onAction(self,action)

    def submit(self):
        self.set = True
        self.doClose()

    def backspace(self):
        self.digits = self.digits[:-1]
        if not self.digits:
            self.doClose()
            return
        self.showChannel()

    def addDecimal(self):
        if '.' in self.digits:
            self.channel = self.channel[:-1]
            self.showChannel()
            return False
        self.digits += '.'
        self.showChannel()
        return True

    def showChannel(self):
        self.channel = self.digits
        try:
            self.setProperty('channel',self.channel)
        except RuntimeError: #Sometimes happens when to fast entry during submission/close
            self.close()

    def getChannel(self):
        if not self.set: return None
        if not self.channel: return None
        if self.channel.endswith('.'):
            return self.channel[:-1]
        return self.channel


class GuideOverlay(util.CronReceiver):
    _BASE = None
    def __init__(self,*args,**kwargs):
        self._BASE.__init__(self,*args,**kwargs)
        self.started = False
        self.touchMode = False
        self.lineUp = None
        self.guide = None
        self.current = None
        self.fallbackChannel = None
        self.cron = None
        self.guideFetchPreviouslyFailed = False
        self.nextGuideUpdate = MAX_TIME_INT
        self.lastDiscovery = time.time()
        self.filter = None

    #==========================================================================
    # EVENT HANDLERS
    #==========================================================================
    def onInit(self):
        self._BASE.onInit(self)
        if self.started: return
        if self.touchMode:
            util.DEBUG_LOG('Touch mode: ENABLED')
            self.setProperty('touch.mode','True')
        else:
            util.DEBUG_LOG('Touch mode: DISABLED')
        self.started = True

        self.propertyTimer = kodigui.PropertyTimer(self._winID,util.getSetting('overlay.timeout',0),'show.overlay','')

        self.channelList = kodigui.ManagedControlList(self,201,3)
        self.currentProgress = self.getControl(250)

        #Add item to dummy list - this list allows right click on video to bring up the context menu
        self.getControl(210).addItem(xbmcgui.ListItem(''))

        self.start()

    def onAction(self,action):
        try:
            if self.overlayVisible(): self.propertyTimer.reset()
            if action == xbmcgui.ACTION_MOVE_RIGHT or action == xbmcgui.ACTION_MOVE_UP or action == xbmcgui.ACTION_MOVE_DOWN:
                return self.showOverlay()
            elif action == xbmcgui.ACTION_CONTEXT_MENU:
                return self.setFilter()
#            elif action == xbmcgui.ACTION_SELECT_ITEM:
#                if self.clickShowOverlay(): return
            elif action == xbmcgui.ACTION_MOVE_LEFT:
                return self.showOverlay(False)
            elif action == xbmcgui.ACTION_PREVIOUS_MENU or action == xbmcgui.ACTION_NAV_BACK:
                if self.closeHandler(): return
            elif action == xbmcgui.ACTION_BUILT_IN_FUNCTION:
                if self.clickShowOverlay(): return
            elif self.checkChannelEntry(action):
                return
        except:
            util.ERROR()
            self._BASE.onAction(self,action)
            return
        self._BASE.onAction(self,action)

    def onClick(self,controlID):
        if self.clickShowOverlay(): return

        if controlID == 201:
            mli = self.channelList.getSelectedItem()
            channel = mli.dataSource
            self.playChannel(channel)

    def onPlayBackStarted(self):
        util.DEBUG_LOG('ON PLAYBACK STARTED')
        self.fallbackChannel = self.current and self.current.dataSource or None
        self.showProgress()

    def onPlayBackStopped(self):
        self.setCurrent()
        util.DEBUG_LOG('ON PLAYBACK STOPPED')
        self.showProgress() #In case we failed to play video on startup
        self.showOverlay()

    def onPlayBackFailed(self):
        self.setCurrent()
        util.DEBUG_LOG('ON PLAYBACK FAILED')
        self.showProgress() #In case we failed to play video on startup
        if self.fallbackChannel:
            channel = self.fallbackChannel
            self.fallbackChannel = None
            self.playChannel(channel)
        util.showNotification(util.T(32023),time_ms=5000,header=util.T(32022))
    # END - EVENT HANDLERS ####################################################

    def onPlayBackEnded(self):
        self.setCurrent()
        util.DEBUG_LOG('ON PLAYBACK ENDED')

    def tick(self):
        if time.time() > self.nextGuideUpdate:
            self.updateChannels()
        else:
            self.updateProgressBars()

    def doClose(self):
        self._BASE.doClose(self)
        self.propertyTimer.stop()
        if util.getSetting('exit.stops.player',True):
            xbmc.executebuiltin('PlayerControl(Stop)') #self.player.stop() will crash kodi (after a guide list reset at least)
        else:
            if xbmc.getCondVisibility('Window.IsActive(fullscreenvideo)'): xbmc.executebuiltin('Action(back)')

    def updateProgressBars(self,force=False):
        if not force and not self.overlayVisible(): return

        if self.current:
            self.currentProgress.setPercent(self.current.dataSource.guide.currentShow().progress() or 0)

        for mli in self.channelList:
            prog = mli.dataSource.guide.currentShow().progress()
            if prog == None:
                mli.setProperty('show.progress','')
            else:
                prog = int(prog - (prog % 5))
                mli.setProperty('show.progress','progress/script-hdhomerun-view-progress_{0}.png'.format(prog))

    def updateChannels(self):
        util.DEBUG_LOG('Updating channels')
        self.updateGuide()
        for mli in self.channelList:
            guideChan = mli.dataSource.guide
            currentShow = guideChan.currentShow()
            nextShow = guideChan.nextShow()
            title = mli.dataSource.name
            thumb = currentShow.icon
            icon = guideChan.icon
            if icon: title = CHANNEL_DISPLAY.format(mli.dataSource.number,title)
            mli.setLabel(title)
            mli.setThumbnailImage(thumb)
            mli.setProperty('show.title',currentShow.title)
            mli.setProperty('show.synopsis',currentShow.synopsis)
            mli.setProperty('next.title',u'{0}: {1}'.format(util.T(32004),nextShow.title or util.T(32005)))
            mli.setProperty('next.icon',nextShow.icon)
            start = nextShow.start
            if start:
                mli.setProperty('next.start',time.strftime('%I:%M %p',time.localtime(start)))
            prog = currentShow.progress()
            if prog != None:
                prog = int(prog - (prog % 5))
                mli.setProperty('show.progress','progress/script-hdhomerun-view-progress_{0}.png'.format(prog))

    def setCurrent(self,mli=None):
        if self.current:
            self.current.setProperty('is.current','')
            self.current = None
        if not mli: return self.setWinProperties()
        self.current = mli
        self.current.setProperty('is.current','true')
        self.setWinProperties()

    def closeHandler(self):
        if self.overlayVisible():
            if not self.player.isPlaying():
                return self.handleExit()
            self.showOverlay(False)
            return True
        else:
            return self.handleExit()

    def handleExit(self):
        if util.getSetting('confirm.exit',True):
            if not xbmcgui.Dialog().yesno(util.T(32006),'',util.T(32007),''): return True
        self.doClose()
        return True


    def fullscreenVideo(self):
        if not self.touchMode and util.videoIsPlaying():
            xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')

    def getLineUpAndGuide(self):
        self.lastDiscovery = time.time()
        self.updateLineup()
        self.showProgress(50,util.T(32008))

        self.updateGuide()
        self.showProgress(75,util.T(32009))
        return True

    def updateLineup(self,quiet=False):
        try:
            self.lineUp = hdhr.LineUp()
        except hdhr.NoCompatibleDevicesException:
            if not quiet: xbmcgui.Dialog().ok(util.T(32016),util.T(32011),'',util.T(32012))
            return False
        except hdhr.NoDevicesException:
            if not quiet: xbmcgui.Dialog().ok(util.T(32016),util.T(32014),'',util.T(32012))
            return False
        except:
            e = util.ERROR()
            if not quiet: xbmcgui.Dialog().ok(util.T(32016),util.T(32015),e,util.T(32012))
            return False

    def updateGuide(self):
        if time.time() - self.lastDiscovery > 3600: #1 hour
            self.updateLineup(quiet=True)

        err = None
        try:
            guide = hdhr.Guide(self.lineUp)
        except hdhr.NoDeviceAuthException:
            err = util.T(32030)
        except:
            err = util.ERROR()

        if err:
            if not self.guideFetchPreviouslyFailed: #Only show notification the first time. Don't need this every 5 mins if internet is down
                util.showNotification(err,header=util.T(32013))
            self.guideFetchPreviouslyFailed = True
            self.nextGuideUpdate = time.time() + 300 #Could not get guide data. Check again in 5 minutes
            self.setWinProperties()
            if self.lineUp.hasGuideData: return
            guide = hdhr.Guide()

        self.guideFetchPreviouslyFailed = False

        self.nextGuideUpdate = MAX_TIME_INT
        for channel in self.lineUp.channels.values():
            guideChan = guide.getChannel(channel.number)
            channel.setGuide(guideChan)
            if channel.guide:
                end = channel.guide.currentShow().end
                if end and end < self.nextGuideUpdate:
                    self.nextGuideUpdate = end

        self.lineUp.hasGuideData = True

        self.setWinProperties()
        util.DEBUG_LOG('Next guide update: {0} minutes'.format(int((self.nextGuideUpdate - time.time())/60)))

    def setWinProperties(self):
        title = ''
        icon = ''
        nextTitle = ''
        progress = None
        channel = ''
        if self.current:
            channel = CHANNEL_DISPLAY.format(self.current.dataSource.number,self.current.dataSource.name)
            if self.current.dataSource.guide:
                currentShow = self.current.dataSource.guide.currentShow()
                title = currentShow.title
                icon = currentShow.icon
                progress = currentShow.progress()
                nextTitle = u'{0}: {1}'.format(util.T(32004),self.current.dataSource.guide.nextShow().title or util.T(32005))

        self.setProperty('show.title',title)
        self.setProperty('show.icon',icon)
        self.setProperty('next.title',nextTitle)
        self.setProperty('channel.name',channel)

        if progress != None:
            self.currentProgress.setPercent(progress)
            self.currentProgress.setVisible(True)
        else:
            self.currentProgress.setPercent(0)
            self.currentProgress.setVisible(False)

    def fillChannelList(self):
        last = util.getSetting('last.channel')

        self.channelList.reset()

        items = []
        for channel in self.lineUp.channels.values():
            guideChan = channel.guide
            currentShow = guideChan.currentShow()
            if self.filter:
                if not channel.matchesFilter(self.filter) and not currentShow.matchesFilter(self.filter): continue
            nextShow = guideChan.nextShow()
            title = channel.name
            thumb = currentShow.icon
            icon = guideChan.icon
            if icon: title = CHANNEL_DISPLAY.format(channel.number,title)
            item = kodigui.ManagedListItem(title,thumbnailImage=thumb,data_source=channel)
            item.setProperty('channel.icon',icon)
            item.setProperty('channel.number',channel.number)
            item.setProperty('show.title',currentShow.title)
            item.setProperty('show.synopsis',currentShow.synopsis)
            item.setProperty('next.title',u'{0}: {1}'.format(util.T(32004),nextShow.title or util.T(32005)))
            item.setProperty('next.icon',nextShow.icon)
            start = nextShow.start
            if start:
                item.setProperty('next.start',time.strftime('%I:%M %p',time.localtime(start)))
            if last == channel.number:
                self.setCurrent(item)
            prog = currentShow.progress()
            if prog != None:
                prog = int(prog - (prog % 5))
                item.setProperty('show.progress','progress/script-hdhomerun-view-progress_{0}.png'.format(prog))
            items.append(item)

        self.channelList.addItems(items)

    def getStartChannel(self):
        util.DEBUG_LOG('Found {0} total channels'.format(len(self.lineUp)))
        last = util.getSetting('last.channel')
        if last and last in self.lineUp:
            return self.lineUp[last]
        elif len(self.lineUp):
            return self.lineUp.indexed(0)
        return None

    def start(self):
        if not self.getLineUpAndGuide(): #If we fail to get lineUp, just exit
            self.doClose()
            return

        for d in self.lineUp.devices.values():
            util.DEBUG_LOG('Device: {0} at {1} with {2} channels'.format(d.ID,d.ip,d.channelCount))

        self.fillChannelList()

        self.player = player.ChannelPlayer().init(self,self.lineUp,self.touchMode)

        channel = self.getStartChannel()
        if not channel:
            xbmcgui.Dialog().ok(util.T(32018),util.T(32017),'',util.T(32012))
            self.doClose()
            return

        if self.player.isPlayingHDHR():
            util.DEBUG_LOG('HDHR video already playing')
            self.fullscreenVideo()
            self.showProgress()
            mli = self.channelList.getListItemByDataSource(channel)
            self.setCurrent(mli)
        else:
            util.DEBUG_LOG('HDHR video not currently playing. Starting channel...')
            self.playChannel(channel)

        self.selectChannel(channel)

        self.cron.registerReceiver(self)

        self.setFocusId(210) #Set focus now that dummy list is ready

    def selectChannel(self,channel):
        pos = self.lineUp.index(channel.number)
        if pos > -1:
            self.channelList.selectItem(pos)

    def showProgress(self,progress='',message=''):
        self.setProperty('loading.progress',str(progress))
        self.setProperty('loading.status',message)

    def clickShowOverlay(self):
        if not self.overlayVisible():
            self.showOverlay()
            self.setFocusId(201)
            return True
        elif not self.getFocusId() == 201:
            self.showOverlay(False)
            return True
        return False

    def showOverlay(self,show=True,from_filter=False):
        if not self.overlayVisible():
            if not from_filter:
                if not self.clearFilter():
                    self.cron.forceTick()
            else:
                self.cron.forceTick()

        self.setProperty('show.overlay',show and 'SHOW' or '')
        self.propertyTimer.reset()
        if show and self.getFocusId() != 201: self.setFocusId(201)

    def overlayVisible(self):
        return bool(self.getProperty('show.overlay'))

    def playChannel(self,channel):
        self.setCurrent(self.channelList.getListItemByDataSource(channel))
        self.player.playChannel(channel)
        self.fullscreenVideo()

    def playChannelByNumber(self,number):
        if number in self.lineUp:
            channel = self.lineUp[number]
            self.playChannel(channel)
            return channel
        return None

    def checkChannelEntry(self,action):
        if action.getId() >= xbmcgui.REMOTE_0 and action.getId() <= xbmcgui.REMOTE_9:
            self.doChannelEntry(str(action.getId() - 58))
            return True
        return False

    def doChannelEntry(self,digit):
        window = KodiChannelEntry(skin.CHANNEL_ENTRY,skin.getSkinPath(),'Main','1080p',digit=digit,has_sub_channels=self.lineUp.hasSubChannels)
        window.doModal()
        channelNumber = window.getChannel()
        del window
        if not channelNumber: return
        util.DEBUG_LOG('Channel entered: {0}'.format(channelNumber))
        if not channelNumber in self.lineUp: return
        channel = self.lineUp[channelNumber]
        self.playChannel(channel)
        self.selectChannel(channel)

    def clearFilter(self):
        if not self.filter: return False
        self.filter = None
        self.current = None
        self.fillChannelList()
        return True

    def setFilter(self):
        terms = xbmcgui.Dialog().input(util.T(32024))
        if not terms: return self.clearFilter()
        self.filter = terms.lower() or None
        self.current = None
        self.fillChannelList()
        self.showOverlay(from_filter=True)
        self.setFocusId(201)


class GuideOverlayWindow(GuideOverlay,BaseWindow):
    _BASE = BaseWindow

class GuideOverlayDialog(GuideOverlay,BaseDialog):
    _BASE = BaseDialog

def start():
    #import os
    #path = os.path.join(util.ADDON.getAddonInfo('profile').decode('utf-8'),'skin')
    util.DEBUG_LOG('Current Kodi skin: {0}'.format(skin.currentKodiSkin()))
    path = skin.getSkinPath()
    if util.getSetting('touch.mode',False):
        window = GuideOverlayWindow(skin.OVERLAY,path,'Main','1080i')
        window.touchMode = True
    else:
        window = GuideOverlayDialog(skin.OVERLAY,path,'Main','1080i')

    with util.Cron(5) as window.cron:
        window.doModal()
        del window