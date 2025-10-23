#!/usr/bin/env python3
import os, re, sys, requests, tkinter, warnings, argparse
import numpy as np
from astropy.table import Table
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning
from astropy.wcs.utils import proj_plane_pixel_scales

warnings.filterwarnings("ignore", category=FITSFixedWarning)

def upload(username, password, tic, toi, directory, group='tfopwg', coverage=None, telsize=None, camera=None, psf=None, deltamag=None, notes=None, skip_summary=False, skip_files=False):
    def _bell():
        try:
            r=tkinter.Tk(); r.withdraw(); r.bell(); r.bell(); r.destroy()
        except Exception:
            pass
    def _err(m):
        print(m); _bell(); sys.exit(1)
    def _arrow_block(rows, arrow="->", extra_pad=2):
        w=max(len(k) for k,_ in rows)
        for k,v in rows: print(f"{k:<{w}}  {arrow}{' '*extra_pad}{v}")

    print("\n===== TFOP SG1 Utility for Uploading Observations to ExoFOP =====")
    if not os.path.isdir(directory): _err("ERROR: Invalid directory.")
    if not telsize: _err("ERROR: Please provide telescope size via --telsize.")
    if not camera:  _err("ERROR: Please provide camera name via --camera.")
    if not coverage: _err("ERROR: Please provide --coverage (Full, Ingress, Egress, or 'Out of Transit').")

    tic_str=str(tic).strip()
    toi_str=str(toi).strip()
    m_tic=re.fullmatch(r'(\d+)\.(\d{2})', tic_str)
    m_toi=re.fullmatch(r'(\d+)\.(\d{2})', toi_str) if toi_str!='0' else None
    if not m_tic or (toi_str!='0' and not m_toi): _err('ERROR: tic and toi must look like "12345678.01" and "1234.01".')
    tic_num, planet_tic=m_tic.group(1), m_tic.group(2)
    if toi_str=='0':
        toi_lbl_display=''
        toi_lbl_upload=''
        target_title=f"TIC {tic_str} (no TOI identifier)"
    else:
        toi_num, planet_toi=m_toi.group(1), m_toi.group(2)
        if planet_tic!=planet_toi: _err("ERROR: Planet indices of tic and toi must match.")
        toi_lbl_display='TOI '+toi_str
        toi_lbl_upload='TOI'+toi_str
        target_title=f"TIC {tic_str} (TOI {toi_str})"
    tgt_prefix=f"TIC{tic_num}-{planet_tic}"

    with requests.Session() as s:
        r=s.post('https://exofop.ipac.caltech.edu/tess/password_check.php',data={'username':username,'password':password,'ref':'login_user','ref_page':'/tess/'})
        if r is None or r.status_code>=400: _err('\nERROR: Login failed.')
        print("Successfully logged in to ExoFOP.")

        files=sorted([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory,f))])
        for f in files:
            if f.endswith('seeing-profile.gif') or ('bjd-flux-err' in f): _err("ERROR: Disallowed file present: "+f)

        base=re.compile(r'^(?P<tgt>TIC\d+)-(?P<pp>\d{2})_(?P<ymd>\d{8})_(?P<obs>[A-Za-z0-9\-]+)_(?P<flt>[A-Za-z0-9\-\+]+)(?:_(?P<px>\d+)px)?_(?P<tail>.+)$')
        allowed_specs={
            r'^measurements_NEBcheck\.zip$':'NEB Depth Plots',
            r'^measurements_NEB-table\.txt$':'NEB Table',
            r'^measurements_dmagRMS-plot\.png$':'Dmag vs. RMS Plot',
            r'^measurements\.tbl$':'AstroImageJ Photometry Measurement Table',
            r'^measurements\.plotcfg$':'AstroImageJ Plot Configuration File',
            r'^measurements\.radec$':'AstroImageJ Photometry Aperture File',
            r'^lightcurve\.png$':'Light Curve Plot',
            r'^compstar-lightcurves\.png$':'Compstar Light Curve Plots',
            r'^field\.png$':'Field Image with Apertures',
            r'^field-zoom\.png$':'Zoomed-in FOV',
            r'^seeing-profile\.png$':'Seeing Profile',
            r'^notes\.txt$':'Notes and Results Text',
            r'^WCS\.fits$':'Plate-Solved Image',
            r'^subset\.csv$':'Photometry Table Subset for Joint Fitting'
        }
        required_keys_per_filter=[
            'AstroImageJ Photometry Measurement Table',
            'AstroImageJ Plot Configuration File',
            'AstroImageJ Photometry Aperture File',
            'Compstar Light Curve Plots',
            'Field Image with Apertures',
            'Zoomed-in FOV',
            'Plate-Solved Image',
            'Seeing Profile'
        ]
        required_global=['Notes and Results Text']
        optional_keys=[v for v in set(allowed_specs.values()) if v not in required_keys_per_filter and v not in required_global]

        recognized, rejected, bases, global_notes=[], [], set(), []
        for fn in files:
            m=base.match(fn)
            if not m: rejected.append((fn,"Name does not match pattern")); continue
            if f"{m.group('tgt')}-{m.group('pp')}"!=tgt_prefix: rejected.append((fn,"TIC/planet mismatch")); continue
            tail=m.group('tail')
            desc=None
            for pat,d in allowed_specs.items():
                if re.fullmatch(pat,tail): desc=d; break
            if not desc: rejected.append((fn,"Unrecognized filetype token")); continue
            ymd,obs,flt,px=m.group('ymd'),m.group('obs'),m.group('flt'),m.group('px') or ''
            bases.add((ymd,obs))
            if desc=='Notes and Results Text': global_notes.append((fn,(ymd,obs)))
            recognized.append({'fn':fn,'desc':desc,'ymd':ymd,'obs':obs,'flt':flt,'px':px})

        if not recognized: _err("ERROR: No recognized files for given TIC/TOI.")
        dates={b[0] for b in bases}; observatories={b[1] for b in bases}
        if len(dates)>1 or len(observatories)>1: _err(f"ERROR: Multiple dates/observatories found: dates={sorted(dates)}, observatories={sorted(observatories)}.")
        date=list(dates)[0]; observatory=list(observatories)[0]
        filter_list=sorted({x['flt'] for x in recognized})
        print(target_title)
        print(f"Detected set -> Date: {date}, Observatory: {observatory}, Filter(s): {', '.join(filter_list)}")

        if len(global_notes)!=1: _err("ERROR: Exactly one notes.txt must be present.")
        for nfn,(nymd,nobs) in global_notes:
            if nymd!=date or nobs!=observatory: _err("ERROR: notes.txt must match the date and observatory of the set.")

        order_types=[
            'AstroImageJ Photometry Measurement Table',
            'AstroImageJ Plot Configuration File',
            'AstroImageJ Photometry Aperture File',
            'Light Curve Plot',
            'Compstar Light Curve Plots',
            'Field Image with Apertures',
            'Zoomed-in FOV',
            'Seeing Profile',
            'Notes and Results Text',
            'Plate-Solved Image',
            'NEB Table',
            'NEB Depth Plots',
            'Dmag vs. RMS Plot',
            'Photometry Table Subset for Joint Fitting'
        ]

        chosen_tbl_by_flt={}
        for flt in filter_list:
            cands=[x for x in recognized if x['flt']==flt and x['desc']=='AstroImageJ Photometry Measurement Table']
            stats=[]
            for x in cands:
                p=os.path.join(directory,x['fn'])
                try:
                    t=Table.read(p,format='ascii.tab',data_start=1)
                except Exception:
                    stats.append((x['fn'],-1e9,1,x['px'])); continue
                med=-1e9; var=1
                if 'Source_Radius' in t.colnames:
                    sr=np.array(t['Source_Radius'],dtype=float)
                    with np.errstate(invalid='ignore'):
                        med=float(np.nanmedian(sr)); vspan=float(np.nanmax(sr)-np.nanmin(sr))
                    var=1 if (np.isnan(vspan) or vspan>0) else 0
                stats.append((x,'med'))
                stats[-1]=(x['fn'],med,var,x['px'])
            if stats:
                stats.sort(key=lambda z:(-z[1],z[2],(-int(z[3]) if z[3].isdigit() else 0),z[0]))
                chosen_tbl_by_flt[flt]=stats[0][0]

        for flt in filter_list:
            found={d:[] for d in set(allowed_specs.values())}
            for x in recognized:
                if x['flt']==flt and x['ymd']==date and x=='': pass
                if x['flt']==flt and x['ymd']==date and x['obs']==observatory: found[x['desc']].append(x['fn'])
            ordered=[]
            for typ in order_types:
                files_of_type=sorted(found.get(typ,[]))
                if typ=='AstroImageJ Photometry Measurement Table' and chosen_tbl_by_flt.get(flt):
                    ct=chosen_tbl_by_flt[flt]
                    if ct in files_of_type:
                        ordered.append((ct,typ))
                        files_of_type=[x for x in files_of_type if x!=ct]
                for fn in files_of_type: ordered.append((fn,typ))
            if ordered:
                w=max(len(f) for f,_ in ordered)
                print(f"\nRecognized files (filter {flt}):")
                for fn,desc in ordered: print(f"  ✔ {fn:<{w}}  ->  {desc}")
        if rejected:
            w=max(len(f) for f,_ in rejected)
            print("\nRejected files (not used):")
            for fn,why in rejected: print(f"  - {fn:<{w}}  ->  {why}")

        missing_by_flt, missing_opt_by_flt={},{}
        for flt in filter_list:
            found={d:[] for d in set(allowed_specs.values())}
            for x in recognized:
                if x['flt']==flt and x['ymd']==date and x['obs']==observatory: found[x['desc']].append(x['fn'])
            req=[k for k in required_keys_per_filter if not found.get(k,[])]
            opt=[k for k in optional_keys if not found.get(k,[])]
            missing_by_flt[flt]=req
            missing_opt_by_flt[flt]=opt

        single_filter=(len(filter_list)==1)
        if not single_filter:
            print("\nGlobal files:")
            print("  ✔ notes.txt found" if len(global_notes)==1 else "  - notes.txt missing")
        for flt in filter_list:
            if missing_opt_by_flt[flt]:
                print(f"\nOptional files not detected (filter {flt}):")
                for k in missing_opt_by_flt[flt]: print("  •",k)
            else:
                print(f"\nOptional files not detected (filter {flt}): None")
        if any(missing_by_flt[flt] for flt in filter_list):
            print("\nMissing required TFOP files:")
            for flt in filter_list:
                if missing_by_flt[flt]:
                    print(f"  Filter {flt}:")
                    for k in missing_by_flt[flt]: print("    •",k)
            if input("Proceed with recognized files anyway? [y/N]: ").strip().lower()!='y': _err("Aborted by user due to missing required TFOP files.")

        cov={'full':'Full','ingress':'Ingress','egress':'Egress','out of transit':'Out of Transit'}.get(coverage.strip().lower(),'Full')
        tag=f"{date}_{username}_tic{tic_num}_{planet_tic}"
        entries_by_flt, found_by_flt={},{}
        if single_filter:
            if psf in (None,""): _err("ERROR: Single-filter run: please supply --psf (e.g., '3.41').")
            if deltamag in (None,""): _err("ERROR: Single-filter run: please supply --deltamag (enter '0' to leave blank).")
            dms=str(deltamag).strip()
            deltamag_single='' if dms=='0' else dms

        for flt in filter_list:
            found={d:[] for d in set(allowed_specs.values())}
            for x in recognized:
                if x['flt']==flt and x['ymd']==date and x['obs']==observatory: found[x['desc']].append(x['fn'])

            meas_candidates=found['AstroImageJ Photometry Measurement Table']
            if not meas_candidates: _err(f"ERROR: No measurement table found for filter {flt}.")
            chosen_tbl=chosen_tbl_by_flt.get(flt) if chosen_tbl_by_flt.get(flt) in meas_candidates else sorted(meas_candidates)[0]
            p=os.path.join(directory,chosen_tbl)
            t=Table.read(p,format='ascii.tab',data_start=1)
            if 'JD_UTC' not in t.colnames: _err(f"ERROR: JD_UTC not found in table (filter {flt}).")
            if 'EXPTIME' in t.colnames: exp0,exp1=float(t['EXPTIME'][0]),float(t['EXPTIME'][-1])
            elif 'EXPOSURE' in t.colnames: exp0,exp1=float(t['EXPOSURE'][0]),float(t['EXPOSURE'][-1])
            else: exp0,exp1=0.0,0.0
            jd0,jd1=float(t['JD_UTC'][0]),float(t['JD_UTC'][-1])
            start=jd0-0.5*exp0/86400.0
            end=jd1+0.5*exp1/86400.0
            obsdur=str(int(round((end-start)*24*60)))
            obsnum=str(len(t))

            wcs_files=[fn for fn in found['Plate-Solved Image']]
            valid_wcs_path=None
            pixscale=''
            for wfn in wcs_files:
                try:
                    with fits.open(os.path.join(directory,wfn)) as h:
                        w=WCS(h[0].header)
                        scales=np.array(proj_plane_pixel_scales(w))*3600.0
                        if np.all(np.isfinite(scales)) and np.all(scales>0):
                            pixscale=f"{float(f'{float(np.mean(scales)):.2g}')}"
                            valid_wcs_path=os.path.join(directory,wfn)
                            break
                except Exception:
                    continue
            if valid_wcs_path is None: _err(f"ERROR: No valid WCS solution found in Plate-Solved Image for filter {flt}.")

            photaprad=''
            var_note=''
            try:
                sr=np.array(t['Source_Radius'],dtype=float)
                med=float(np.nanmedian(sr))
                photaprad=str(round(med,1))
                with np.errstate(invalid='ignore'):
                    vspan=float(np.nanmax(sr)-np.nanmin(sr))
                if not np.isnan(vspan) and vspan>0: var_note='aperture radius was variable in time'
            except Exception:
                pass

            if single_filter:
                psf_final=str(psf).strip()
                deltamag_final=deltamag_single
            else:
                while True:
                    psf_in=input(f"Estimated PSF (arcsec) for filter {flt} (e.g., 3.41): ").strip()
                    try: float(psf_in); psf_final=psf_in; break
                    except: print("Please enter a numeric value.")
                while True:
                    dm_in=input(f"Faintest Neighbor delta Mag for filter {flt} (blank to leave empty): ").strip()
                    if dm_in=='': deltamag_final=''; break
                    try: float(dm_in); deltamag_final=dm_in; break
                    except: print("Please enter a numeric value or leave blank.")

            notes_final=(notes or '').strip()
            if var_note: notes_final=f"{notes_final}; {var_note}" if notes_final else var_note

            entries={
                'planet':toi_lbl_upload,
                'tel':observatory,
                'telsize':str(telsize),
                'camera':camera,
                'filter':flt,
                'pixscale':pixscale,
                'psf':psf_final,
                'photaprad':photaprad,
                'obsdate':f"{date[:4]}-{date[4:6]}-{date[6:]}",
                'obsdur':obsdur,
                'obsnum':obsnum,
                'obstype':'Continuous',
                'transcov':cov,
                'deltamag':deltamag_final,
                'tag':tag,
                'groupname':group,
                'notes':notes_final,
                'id':tic_num
            }
            entries_by_flt[flt]=entries
            found_by_flt[flt]=found

            rows=[
                ("Name",f"TIC {tic_num}.{planet_tic}"),
                ("TOI",toi_lbl_display),
                ("User",username),
                ("Telescope",f"{observatory} ({telsize} m)"),
                ("Camera",camera),
                ("Filter",flt),
                ("Pixel scale (arcsec)",entries['pixscale']),
                ("Estimated PSF (arcsec)",psf_final),
                ("Photometric Aperture Radius (pixel)",(str(int(round(float(photaprad)))) if photaprad!='' else '')),
                ("Transit Coverage",cov),
                ("Faintest Neighbor delta Mag",entries['deltamag']),
                ("Observation date (UT)",entries['obsdate']),
                ("Observation duration (m)",entries['obsdur']),
                ("Number of Observations",entries['obsnum']),
                ("Observation Type","Continuous"),
                ("Notes",entries['notes']),
                ("Group",group),
                ("Tag",tag),
            ]
            print(f"\nObservation Summary (filter {flt}):")
            _arrow_block(rows,arrow="->",extra_pad=2)

        if skip_summary and skip_files:
            print("\nUploads are disabled by settings (both --skip-summary and --skip-files were set). Nothing will be uploaded.")
            return

        ans=input("\nPress Enter to submit the time-series summaries and upload recognized files to ExoFOP, or type 'n' to cancel: ").strip().lower()
        if ans=='n': _err("User cancelled before uploads.")

        for flt in filter_list:
            entries=entries_by_flt[flt]
            found=found_by_flt[flt]
            if not skip_summary:
                r=s.post('https://exofop.ipac.caltech.edu/tess/insert_tseries.php',data=entries)
                if r is None or r.status_code>=400: _err(f'\nERROR: Time Series Add failed (filter {flt}).')
            if not skip_files:
                meas_candidates=sorted(found.get('AstroImageJ Photometry Measurement Table',[]))
                chosen_tbl=chosen_tbl_by_flt.get(flt)
                ordered=[]
                if chosen_tbl and chosen_tbl in meas_candidates:
                    ordered.append((chosen_tbl,'AstroImageJ Photometry Measurement Table'))
                    for fn in [x for x in meas_candidates if x!=chosen_tbl]: ordered.append((fn,'AstroImageJ Photometry Measurement Table'))
                else:
                    for fn in meas_candidates: ordered.append((fn,'AstroImageJ Photometry Measurement Table'))
                for typ in order_types[1:]:
                    for fn in sorted(found.get(typ,[])): ordered.append((fn,typ))
                for fn,desc in ordered:
                    p=os.path.join(directory,fn)
                    r=s.post('https://exofop.ipac.caltech.edu/tess/insert_file.php',files={'file_name':open(p,'rb')},data={'file_type':'Light_Curve','planet':entries['planet'],'file_desc':desc,'file_tag':entries['tag'],'groupname':entries['groupname'],'propflag':'on','tid':entries['id']})
                    if r is None or r.status_code>=400: _err(f'\nERROR: File upload failed: {fn}')
        print("All requested uploads completed.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description="TFOP SG1 Utility for Uploading Observations to ExoFOP (updated naming, per-filter summaries/uploads).")
    ap.add_argument("--username",required=True)
    ap.add_argument("--password",required=True)
    ap.add_argument("--tic",required=True)
    ap.add_argument("--toi",required=True)
    ap.add_argument("--directory",required=True)
    ap.add_argument("--coverage",required=True)
    ap.add_argument("--telsize",required=True)
    ap.add_argument("--camera",required=True)
    ap.add_argument("--psf")
    ap.add_argument("--deltamag")
    ap.add_argument("--notes")
    ap.add_argument("--skip-summary",dest="skip_summary",action="store_true")
    ap.add_argument("--skip-files",dest="skip_files",action="store_true")
    args=ap.parse_args()
    upload(username=args.username,password=args.password,tic=args.tic,toi=args.toi,directory=args.directory,group="tfopwg",coverage=args.coverage,telsize=args.telsize,camera=args.camera,psf=args.psf,deltamag=args.deltamag,notes=(args.notes or None),skip_summary=args.skip_summary,skip_files=args.skip_files)
