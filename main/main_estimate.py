#%%
# === Dependencies ===
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.api import VAR, acf
import numpy as np
import matplotlib.pyplot as plt
import sys
from typing import Union
from statistics import NormalDist
from tqdm import tqdm

#%%
# === Data (index = HICP & Qt without log transf.) ===
df_w = pd.read_excel("data/data_flat.xlsx",sheet_name="weights")
df_q_index = pd.read_excel("data/data_flat.xlsx",sheet_name="QT_index")
df_p_index = pd.read_excel("data/data_flat.xlsx",sheet_name="P_index")
#```
df_q_index.replace("European Union - 27 countries (from 2020)","EU27",inplace=True)
df_p_index.replace("European Union - 27 countries (from 2020)","EU27",inplace=True)
df_p_index = df_p_index.drop(['2023-10'],axis=1)
df_w.replace("European Union - 27 countries (from 2020)","EU27",inplace=True)

def log_transform(cell_value):
    try:
        return np.log(float(cell_value))
    except (ValueError, TypeError):
        return cell_value    

# ===============================================================
# ===============================================================
#TODO: télécharger overall HICP monthly pour voir quel % décomposé

#TODO ///sector_estimation///
#* SVAR_Shapiro_exp.pdf pour l'explication
#* Sheremirov labeling
#* Shapiro smooth(1-3)
#*: Shapiro robustness : Parametric weights

#TODO ///CPIlabel///
#TODO: la décomposition
#TODO: monthly weights ???

# ===============================================================
# ===============================================================

#%%
#! //////////////////////////
class CPIframe:
    def __init__(self, df_q_index, df_p_index, df_w, country, start_flag=[2000,2001],end_flag=2023):
        """
        Args:
        - `df_q_index` (DataFrame): The Quantity data (index)
        - `df_p_index` (DataFrame): The Price data (index)
        - `df_w` (DataFrame): The respective Weights data
        - `country` (str): Location choice (EU27,France,Germany,Spain)
        - `start_flag`
        - `end_flag`
        """
        self.country = country
        self.qt = self.framing(df=df_q_index,transform=True)    #Log-transformed
        self.price = self.framing(df=df_p_index,transform=True) #Log-transformed
        self.qt_index = self.framing(df=df_q_index)
        self.price_index = self.framing(df=df_p_index)
        self.weights = self.framing(df=df_w)
        self.sectors = dict(self.qt.loc['HICP'])
        self.dates = pd.to_datetime(list(self.price.index)[1::])
        self.inflation = self.inflation()
        self.start_flag = start_flag
        self.end_flag = end_flag
        self.flag = self.flag_sector(start=self.start_flag, end=self.end_flag)
        
    def framing(self,df,transform=False,variation=False):
        """
        Generates a subset of the dataframe `df` based on the specified `country`.
        'df' = df_p_index or df_q_index or df_w > from excel data_flat
        Parameters:
            df: pandas.DataFrame
            transform: log transform if True
        Returns:
            pandas.DataFrame: Dataframe of Quantity or Price series data with dates as rows.
        """
        if transform==True:
            temp = df.applymap(log_transform)
        elif variation==True:
            temp = df.applymap(log_transform)
        else:
            temp = df.copy()
        x = temp[temp['Location']==self.country]
        x.reset_index(drop=True,inplace=True)
        x = x.drop(['Location'],axis=1)
        x = x.transpose()
        return x
        
    def sector(self,col_num,indexx=False,transform=True,weights=False):
        """
        Generates a [price,quantity] table for the specified sector.
        Parameters:
            col_num: column number in `price` & `qt` objects for the sector of interest.
            indexx: if False takes data from log-dataset (self.price & self.qt)
            transform: (requires indexx=False)
                    if True: 
                    1. 100*first_diff 
                    2. Demean
            weights: if True returns subset of self.weights for col_num
        Returns:
            pandas.DataFrame: Dataframe of Quantity series data with dates as rows
        """
        if not weights:
            if indexx==False:
                x = pd.concat([self.price[col_num],self.qt[col_num]],axis=1)
                sec = list(x.loc['HICP'])[-1]
                x = x.drop(['HICP'],axis=0)
                x.columns = ['price','qt']
                x = x.apply(pd.to_numeric)
                
                if transform:
                    x = 100*x.diff() 
                    x = x - x.mean()
                x = x.dropna()
                x.coicop = sec
                x.col = col_num
                x.index = pd.to_datetime(x.index)
                return x
            
            else:
                x = pd.concat([self.price_index[col_num],self.qt_index[col_num]],axis=1)
                sec = list(x.loc['HICP'])[-1]
                x = x.drop(['HICP'],axis=0)
                x.columns = ['price','qt']
                x = x.apply(pd.to_numeric)
                
                x = x.dropna()
                x.coicop = sec
                x.col = col_num
                x.index = pd.to_datetime(x.index)
                return x
        
        else:
            x = self.weights[[col_num]]
            sec = list(x.loc['HICP'])[-1]
            x = x.drop(['HICP'],axis=0)
            x.coicop = sec
            x.index = pd.to_datetime(x.index)
            return x
    
    def inflation(self):
        x = pd.DataFrame()
        for col in self.price_index.columns:
            temp = self.price_index[[col]]
            temp = temp.drop(['HICP'],axis=0).dropna()
            temp.index = pd.to_datetime(temp.index)
            temp = 100*temp.pct_change().dropna() #monthly rate
            temp = temp.reindex(self.dates)
            x[col] = temp
        return x
    
    def sector_inf(self,col_num,drop=True):
        x = pd.DataFrame()
        x['inflation'] = self.inflation[[col_num]]
        x.index = pd.to_datetime(x.index)
        x["temp"] = x.index.year
        x["weight"] = x["temp"].apply(lambda x: self.weights.loc[x,col_num])
        x = x.drop("temp",axis=1)
        x["infw"] = x["inflation"]*x["weight"]
        if drop==True:
            x = x.drop(['inflation','weight'],axis=1)
        return x

    def flag_sector(self,start,end):
        """
        - Checks if 'enough' data for each sector
        """
        L = len(self.price.columns)
        flag = {x:None for x in range(L)}
        for i in range(L):
            x = self.sector(col_num=i)
            if len(x)!=0:
                if end==x.index[-1].year:
                    if any(yr==x.index[0].year for yr in start):
                        flag[i] = 0
        flag = {key: value if value is not None else 1 for key, value in flag.items()}
        return flag
        
    def flag_summary(self):
        """
        Summary of flag sector.
        """
        names = self.price.loc['HICP']
        for i in range(len(self.price.columns)):
            x = self.sector(col_num=i)
            if len(x)!=0:
                if self.end_flag==x.index[-1].year:
                    if any(yr==x.index[0].year for yr in self.start_flag):
                        print(i," : OK ",x.index[0].year,"-",x.index[0].month,";",x.index[-1].year,"-",x.index[-1].month," -- ",len(x)," obs. -- ",names[i])
                else:
                    print(i," : end missing -",x.index[0].year,"-",x.index[0].month,";",x.index[-1].year,"-",x.index[-1].month," -- ",names[i])
            else:
                if len(self.qt[i].dropna()) == 1 and len(self.price[i].dropna()) > 1:
                    print(i,' : PB QT ','-- price :',self.price[i].dropna().index[1],';',self.price[i].dropna().index[-1]," -- ",names[i])
                elif len(self.price[i].dropna()) == 1 and len(self.qt[i].dropna()) > 1:
                    print(i,' : PB PRICE','-- qt :',self.qt[i].dropna().index[1],';',self.qt[i].dropna().index[-1]," -- ",names[i])
                else:
                    print(i," : PB price & qt -- ",names[i])


#! //////////////////////////
class sector_estimation:
    def __init__(self,meta:CPIframe,col:int,
                 order:Union[int, str]="auto",maxlag=24,trend="n",
                 shapiro:bool=True,
                 shapiro_robust:bool=False,
                 sheremirov:bool=True,
                 sheremirov_window:list=[1,11],
                 classify_inflation=True):
        """
        Args:
            - `meta`: `CPIframe` object
            - `col`: sector column number in [0,93]
            - If too litte data for sector 'col' then raises ValueError
            - VAR model is built with first diff then demeand log-transformed data
            - `classify_inflation`: if False only returns Shapiro and Sheremirov classification in binary form. Otherwise returns 1(dem)*weight*inf_rate / 1(sup)*w*inf_rate
                
            `VAR parametrization`
            order: if "auto" VAR order is automatically selected. Else requires an integer
            maxlag: higher bound of order selection
            trend: should remain "n" because data have been demeaned and are supposed to be stationary (no trend)
            
            `Labeling methods`
            shapiro: if True computes baseline Shapiro(2022) labeling method with reduced-form estimated VAR
            shapiro_robustness: if True also computes alternative labeling methodologies
            sheremirov: if True computes baseline Sheremirov(2022) labeling method
            sheremirov_window: [Transitory,Persistent] parametrization of step classification algo step5 
        """
        self.meta = meta    
        self.col = col
        
        #* VAR model will use log-transformed first diff and demeaned data 
        self.sector = meta.sector(col_num=col,transform=True)
        self.inflation = meta.sector_inf(col_num=col,drop=True)
        #!
        self.classify_inflation = classify_inflation            
        
        #! Flag sector
        if len(self.sector) <= 24:
            raise ValueError("Too little data for sector {0}".format(self.col))
        #````
        self.sector_w = meta.sector(col_num=col,weights=True)
        self.sector_dates = {i:x for i,x in enumerate(list(self.sector.index))}
        self.sector_index = meta.sector(col_num=col, indexx=True)
        self.order = order
        self.maxlag = maxlag
        self.trend = trend
        self.sec_name = self.meta.sectors[self.col]
        #````
        if self.order!="auto" and type(self.order)!=int:
            raise ValueError('Order should be set to "auto" or entered as an integer')
        
        self.sector_ts = self.sector.reset_index(drop=True)
        self.model = VAR(endog=self.sector_ts)
        self.estimation = self.run_estimate()
        if self.order=="auto":
            self.aic = self.estimation['aic']
            self.bic = self.estimation['bic']
            #? Shapiro
            if shapiro:
                self.aic.shapiro = self.shapiro_label(model_resid=self.aic.resid)
                self.bic.shapiro = self.shapiro_label(model_resid=self.bic.resid)
                if shapiro_robust:
                    self.aic.shapiro_robust = self.shapiro_robust(model_resid=self.aic.resid)
                    self.bic.shapiro_robust = self.shapiro_robust(model_resid=self.bic.resid)
        else:
            self.estimate = self.estimation['fixed']
            #? Shapiro
            if shapiro:
                self.estimate.shapiro = self.shapiro_label(model_resid=self.estimate.resid)
                if shapiro_robust:
                    self.estimate.shapiro_robust = self.shapiro_robust(model_resid=self.estimate.resid)
            
        #? Sheremirov
        if sheremirov:
            self.sheremirov_window = sheremirov_window
            self.sheremirov = self.sheremirov_label(transitory=self.sheremirov_window)
        
    def run_estimate(self):
        """
        Does not need to be called outside of the class definition.
        Output is a dictionary {'aic':model.fit,'bic':model.fit} where model.fit 
        """
        model_fit = {'aic':None,'bic':None, 'fixed':None}
        if self.order == "auto":
            for crit in ['aic','bic']:
                model_fit[crit] = self.model.fit(maxlags=self.maxlag,ic=crit,trend=self.trend)
        else:
            model_fit["fixed"] = self.model.fit(self.order,trend=self.trend)
        return model_fit

    def shapiro_label(self,model_resid):
        """
        Adapted from Shapiro (2022):
        - Uses residuals of a reduced-form VAR
            - Input requires stationary series
            - Data processing: 
                - 1)[log(Price_index),log(Qt_index)] 
                - 2) 100*(first_diff) 
                - 3) Demean
            - Final series should be +/- stationary
        > Expected comovements can be infered from reduced-form residuals via sign restrictions.
            - cf. `SVAR_shapiro_exp.pdf`
        """
        x = model_resid.copy()
        x[["dem","sup","dem+","dem-","sup+","sup-"]] = ""
        # demand shock
        x['dem+'] = np.where((x['qt']>0) & (x['price']>0),1,0)
        x['dem-'] = np.where((x['qt']<0) & (x['price']<0),1,0)
        # supply shock
        x['sup+'] = np.where((x['qt']>0) & (x['price']<0),1,0)
        x['sup-'] = np.where((x['qt']<0) & (x['price']>0),1,0)
        x['dem'] = x['dem+'] + x['dem-']
        x['sup'] = x['sup+'] + x['sup-']
        x = x.drop(['price','qt'],axis=1)
        #changes index from int to original date & uses all dates
        x.index = x.index.map(self.sector_dates)
        x = x.reindex(self.meta.dates)               
        if self.classify_inflation==False:
            #To decerase storage size
            for col in x.columns:
                x[col] = x[col].astype('Int8')
        else:
            for col in x.columns:
                x[col] = x[col]*self.inflation['infw']
        return x

    def shapiro_robust(self,model_resid):
        """
        Adapted from Shapiro (2022):
        - Smoothed labeling method
        - Parametric weights
        """
        x = model_resid.copy()
        for j in range(4):  
            #j=0 is baseline shapiro
            temp = x[['price','qt']].copy()
            temp[["temp_p","temp_q"]] = temp[['price','qt']].rolling(j+1).sum()
            temp = temp.dropna()
            temp["dem"] = np.where(((temp['temp_p']>0) & (temp['temp_q']>0)) | ((temp['temp_p']<0) & (temp['temp_q']<0)),1,0)
            temp["sup"] = np.where(((temp['temp_p']>0) & (temp['temp_q']<0)) | ((temp['temp_p']<0) & (temp['temp_q']>0)),1,0)
            if j==0:
                x[["dem","sup"]] = temp[["dem","sup"]]
            else:
                x[["dem_j{0}".format(j),"sup_j{0}".format(j)]] = temp[["dem","sup"]]
        x["lambda"] = x['price']*x['qt']
        x["lambda"] = x["lambda"]*(1/x["lambda"].std())
        x["dem_param"] = x["lambda"].apply(lambda x: NormalDist().cdf(x))
        x["sup_param"] = 1 - x["dem_param"]
        x = x.drop(['price','qt','lambda'],axis=1)
        #changes index from int to original date & uses all dates
        x.index = x.index.map(self.sector_dates)     
        x = x.reindex(self.meta.dates)
        if self.classify_inflation==False:  
            #To decerase storage size
            for col in x.columns:
                if col not in ["dem_param","sup_param"]:
                    x[col] = x[col].astype('Int8')
        else:
            for col in x.columns:
                x[col] = x[col]*self.inflation['infw']
        return x
       
    def sheremirov_label(self,transitory):
        """
        Adapted from Sheremirov (2022):
        - Uses deviation of growth rates of HICP & Demand proxy compared to 2000-19 mean
        """
        x = self.sector_index.copy()
        x = 100*x.pct_change(12).dropna()
        #``` Remove 2000-2019 mean
        x['yr'] = x.index.year
        m = x[(x['yr']<=2019)&(x['yr']>=2000)].drop("yr",axis=1).mean()
        x = x.drop('yr',axis=1)
        x = x - m
        #```
        x[["dem","sup","dem_pers","dem_trans","sup_pers","sup_trans"]] = ""
        x["dem"] = np.where((x['qt']>0) & (x['price']>0),1,0)
        x["sup"] = 1 - x["dem"]
        x["temp"] = x["dem"].rolling(12).sum()
        x["dem_pers"] = np.where((x['dem']==1) & (x['temp']>=transitory[1]),1,0)
        x["sup_pers"] = np.where((x['dem']==0) & (x['temp']<=transitory[0]),1,0)
        x["dem_trans"] = np.where((x['dem']==1) & (x['temp']<transitory[1]),1,0)
        x["sup_trans"] = np.where((x['dem']==0) & (x['temp']>transitory[0]),1,0)
        x = x.drop(['price','qt','temp'],axis=1)
        x = x.reindex(self.meta.dates)
        if self.classify_inflation==False:
            for col in x.columns:
                x[col] = x[col].astype('Int8')
        else:
            for col in x.columns:
                x[col] = x[col]*self.inflation['infw']
        return x


#! //////////////////////////
#TODO: /!\ décomposition du overall HICP car secteurs pas même VAR_order donc classification commence pas en même temps!
#TODO: Pb comment combiner les différents tableaux output shapiro/sheremirov
class CPIlabel:
    def __init__(self,meta:CPIframe,
                 order:Union[int, str]="auto",maxlag=24,
                 shap_robust:bool=True,
                 sheremirov_window:list[int,int]=[1,11]):
        """
        Args:
            - `meta`: `CPIframe` object
            - `order`: if "auto" VAR order is automatically selected. Else requires an integer
            - `maxlag`: higher bound of order selection (if order="auto")
            - `shap_robustness`: if True also computes alternative labeling methodologies
            - `sheremirov_window: [Transitory,Persistent] parametrization of step classification algo step5 
            -  NB1: VAR models are built with first diff then demeand log-transformed data
        """
        self.meta=meta
        self.order=order
        self.maxlag=maxlag
        self.shap_robust=shap_robust
        self.sheremirov_window=sheremirov_window
        self.sheremirov = pd.DataFrame(columns=pd.MultiIndex.from_tuples([], names=['Sector','Component']))
        if self.order=="auto":
            self.shapiro_aic = None
            self.shapiro_bic = None
            if shap_robust:
                self.shapiro_aic_r = None
                self.shapiro_bic_r = None
        else:
            self.shapiro = None
            if shap_robust:
                self.shapiro_r = None
        self.CPIdec = self.CPI_decompose()

    
    def CPI_decompose(self):
        print('>> CPI decomposition for {0} processing'.format(self.meta.country))
        c = []
        L = len(self.meta.price.columns)
        if self.order=="auto":
            temp_shapiro_aic = {}
            temp_shapiro_bic = {}
            if self.shap_robust:
                temp_shapiro_aic_r = {}
                temp_shapiro_bic_r = {}
        else:
            temp_shapiro = {}
            if self.shap_robust:
                temp_shapiro_r = {}

        with tqdm(total=L, ascii=True) as pbar:
            for col in range(0,L):
                if self.meta.flag[col]==1:
                    # Sector was flagged as missing some data
                    pass
                else:
                    c.append(col)
                    estimator = sector_estimation(meta=self.meta, col=col, order=self.order, maxlag=self.maxlag, shapiro_robust=self.shap_robust, sheremirov_window=self.sheremirov_window, classify_inflation=True)
                    if self.order=="auto":                    
                        temp_shapiro_aic[col] = estimator.aic.shapiro
                        temp_shapiro_bic[col] = estimator.bic.shapiro
                        if self.shap_robust:
                            temp_shapiro_aic_r[col] = estimator.aic.shapiro_robust
                            temp_shapiro_bic_r[col] = estimator.bic.shapiro_robust
                    else:
                        temp_shapiro[col] = estimator.estimate.shapiro
                        if self.shap_robust:
                            temp_shapiro_r[col] = estimator.estimate.shapiro_robust
                pbar.update(1)
        if self.order=="auto":
            self.shapiro_aic = pd.concat([x.transpose().stack() for x in temp_shapiro_aic.values()], keys=c, names=['Sector']).unstack().transpose()
            self.shapiro_bic = pd.concat([x.transpose().stack() for x in temp_shapiro_bic.values()], keys=c, names=['Sector']).unstack().transpose()
            if self.shap_robust:
                self.shapiro_aic_r = pd.concat([x.transpose().stack() for x in temp_shapiro_aic_r.values()], keys=c, names=['Sector']).unstack().transpose()
                self.shapiro_bic_r = pd.concat([x.transpose().stack() for x in temp_shapiro_bic_r.values()], keys=c, names=['Sector']).unstack().transpose()
        else:
            self.shapiro = pd.concat([x.transpose().stack() for x in temp_shapiro.values()], keys=c, names=['Sector']).unstack().transpose()
            if self.shap_robust:
                self.shapiro_r = pd.concat([x.transpose().stack() for x in temp_shapiro_r.values()], keys=c, names=['Sector']).unstack().transpose()
        return()

    
#df['Sum_Columns'] = df['Column1'].fillna(0) + df['Column2'].fillna(0)
     
#%%
#? =====================================================================
eu = CPIframe(df_q_index=df_q_index, df_p_index=df_p_index, df_w=df_w, country="EU27")
t1 = sector_estimation(meta=eu,col=64,shapiro_robust=True)
t2 = sector_estimation(meta=eu,col=11,shapiro_robust=True)
cpi_eu = CPIlabel(meta=eu)

#%%
duo = ['Sector', 'Component']
#test = pd.MultiIndex.from_tuples([], names=duo)
#test = test.append(pd.MultiIndex.from_tuples([(64,j) for j in t1.aic.shapiro_robust], names=duo))
multi_index = pd.MultiIndex.from_product([['aic', 'bic'], t1.aic.shapiro_robust.columns], names=duo)
test = pd.concat([t1.aic.shapiro_robust.transpose().stack(), t1.bic.shapiro_robust.transpose().stack()], keys=['aic', 'bic'], names=['Sector']).unstack()
#df_multi_combined = pd.concat([df_multi, df_c.stack()], keys=['C'], names=['Letter']).unstack()
test = test.transpose()

#%%






#%%
#eu.flag_sectors()

"""
for i in range(len(eu.price.columns)):
    x = eu.sector(col_num=i).dropna()
    if len(x)!=0:
        if "2023" in x.index[-1]:
            if "2000" or "2001" in x.index[0]:
                print(i," : ",x.index[0]," - ",x.index[-1]," -- ",len(x)," -- ",names[i])
        else:
            print(i," : LATE -",x.index[0]," - ",x.index[-1]," -- ",len(x)," -- ",names[i])
    else:
        #print(i,'PB -- qt ',len(eu.qt[i].dropna()), ' -- price ',len(eu.price[i].dropna())," -- ",names[i])
        if len(eu.qt[i].dropna()) == 1 and len(eu.price[i].dropna()) > 1:
            print(i,'PB QT ','-- price :',eu.price[i].dropna().index[1],' - ',eu.price[i].dropna().index[-1]," -- ",names[i])
        elif len(eu.price[i].dropna()) == 1 and len(eu.qt[i].dropna()) > 1:
            print(i,'PB PRICE','-- qt :',eu.qt[i].dropna().index[1],' - ',eu.qt[i].dropna().index[-1]," -- ",names[i])
        else:
            print(i,"PB price & qt -- ",names[i])
"""

#print(estimation_test.aic.plot_acorr(25))
#restest = etest.aic.resid
#test = eu.sector(56,False)[['price']].copy()
#cycle, trend = sm.tsa.filters.hpfilter(test, 1600*3**4)

